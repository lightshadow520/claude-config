# HPC 与远程服务器操作规则

本文件在 CLAUDE.md 触发关键词匹配时加载，覆盖 SSH 诊断、进程管理、计算任务提交。

---

# SSH 连接方式（强制规则）

## 优先使用 paramiko，禁止依赖 sshpass

`sshpass` 在不同平台（WinGet/apt/brew）行为不一致，密码传递经常失败。**默认使用 Python paramiko 库连接远程服务器**：

```python
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, port=port, username=user, password=pw, timeout=15)
stdin, stdout, stderr = c.exec_command('command')
```

paramiko 是纯 Python 实现，不依赖系统 SSH 或 sshpass，跨平台一致。已在多台 AutoDL/GPUshare 服务器验证通过。

**只有在 paramiko 也失败时才尝试 sshpass**：
```
sshpass -p 'password' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 user@host -p port 'command'
```

**严禁**：用 `echo password | ssh` 管道方式传密码（ssh 不支持 stdin 密码输入）。

## 连接超时 ≠ 服务器挂了

用户的计算任务（CP2K/VASP 等）会让 CPU 跑满（load average = 核数），
SSH daemon 也是用户态进程，CPU 被抢光时 SSH 握手会超时。

**遇到 SSH 连接失败时，禁止直接说"换服务器"。必须按以下步骤：**

1. 先试**更长的超时**（ConnectTimeout=30s 甚至 60s），不要用默认 10s
2. 同一个 host 的不同端口各试一次（不同端口的负载可能不同）
3. 如果某个端口连不上，但同一 host 的其他端口能连 → 说明服务器没挂，只是那个端口对应的实例 CPU 满了
4. 只有**所有端口**都连不上 + 长超时也失败，才能说服务器可能有问题
5. 询问用户"你那边能直接 SSH 上去吗"比直接断言服务器挂了更合适

**严禁行为：**
- 一次连接失败就直接说"XX 服务器断了，换一台"
- 在没确认之前建议用户杀进程、重启服务器
- 不尝试其他端口就下结论

---

# 远程服务器进程管理（强制规则）

对远程 Linux 服务器执行任何进程操作前，**必须先用 `remote_ps.py` 获取结构化进程清单**。

**禁止直接 SSH 执行 `ps aux` 然后人工分析输出。** 原始 `ps aux` 输出在上下文窗口中极易导致：
- 遗漏僵尸进程（混在正常输出中不可见）
- 误判进程归属（多用户/多任务时看不清谁是谁）
- 上下文爆炸（200+ 行进程列表吞噬 token 预算）

## 查看进程

```
python <scripts_dir>/remote_ps.py --host <host>                        # 结构化概览
python <scripts_dir>/remote_ps.py --host <host> --diagnose             # 概览 + 自动诊断
python <scripts_dir>/remote_ps.py --host <host> --json                 # 结构化 JSON
python <scripts_dir>/remote_ps.py --host <host> --port <port> --user <user>
python <scripts_dir>/remote_ps.py --host <host> --method ssh           # 用系统 SSH
python <scripts_dir>/remote_ps.py --host <host> --timeout 60           # 长超时
```

### 输出分组

| 分组 | 含义 |
|------|------|
| 🟢 Computing tasks | 正在运行的计算（VASP/CP2K/Gaussian/ORCA/LAMMPS/GROMACS 等） |
| 🧟 Zombie / defunct | 僵尸进程，父进程未回收 |
| 🔴 High-resource | CPU>80% 或 MEM>30% 的非计算进程 |
| ⚪ System / idle | 系统进程和空闲进程（折叠按可执行文件分组） |

### 触发场景

- 用户要求查看远程服务器进程、服务器上在跑什么
- 用户想确认某个计算是否还在运行
- **任何涉及远程进程的 kill/stop/restart 操作前**（先看全貌再动手）
- SSH 连接失败时排查是否因为 CPU 满载

## 终止进程（强制审批）

终止远程进程前必须按以下步骤操作：

1. **先跑 `remote_ps.py --host <host> --diagnose`** 获得完整进程清单
2. **列出所有相关进程**（计算主进程 + 子进程 + 僵尸 + 关联进程），标注 PID 和父子关系
3. **明确告知用户**哪些会被杀掉、哪些会保留、杀完后预期状态
4. **得到用户确认后**才能执行 `kill <PID>`（逐个杀，**严禁使用 `killall`/`pkill` 批量杀**）
5. 杀完后**再次跑 `remote_ps.py --host <host>`** 验证结果

### 严禁行为

- **禁止**直接 SSH 执行 `ps aux` 然后人工分析
- **禁止**在不知道全部僵尸/孤儿进程的情况下杀进程
- **禁止**用 `killall`、`pkill`、`kill -9 *` 等批量命令远程杀进程
- **禁止**凭进程 CPU 占用率或运行时间猜测"这个应该已经挂了"
- **禁止**同一台服务器上既有计算任务又想清理时，不区分计算进程和僵尸进程

## 杀进程 ≠ 删文件（强制规则）

**杀掉计算进程后，严禁随意删除工作目录中的任何文件。**

### 严禁删除的文件

- VASP: `OUTCAR` `OSZICAR` `vasp.log` `WAVECAR` `CHGCAR` `CHG` `CONTCAR` `DOSCAR` `EIGENVAL` `XDATCAR`
- CP2K: `.restart` `.wfn` `.out` `coord.xyz`（CP2K 续算依赖 `.restart` 和 `.wfn`，删除后进度全部丢失）
- 通用: `POSCAR` `INCAR` `KPOINTS` `POTCAR` `run_*.sh` `*.inp` `make_potcar.sh` `.hpc_status.json`

### 正确做法

1. **杀进程只杀进程**：`kill <PID>` 或通过 `hpc_job.py kill`，不碰任何文件
2. **旧输出归档而非删除**：如确实需要清理，移到带时间戳的子目录（如 `old_outputs_20260603/`），不要 `rm`
3. **需要删文件时**：先列出所有将被删除的文件 + 各自的作用 + 删除原因，**等用户确认后再删**
4. **CP2K 续算铁律**：`.restart` 和 `.wfn` 绝对不能删——这些是检查点，删除后几何优化进度归零

---

# HPC 计算任务管理（强制规则）

**绝对不要让 AI 直接执行 `nohup mpirun ... &` 或裸 SSH 跑计算。**
必须通过 HPC 中间件（hpc_watcher.py + hpc_job.py）进行操作。

## 架构

```
AI (Claude)
  │
  ├─ hpc_job.py (本地) ── SSH ──→ hpc_watcher.py (服务器)
  │                                    │
  │   submit / check / kill / logs      ├─ 心跳监控 (文件 mtime)
  │   --host node01 --dir /path         ├─ OOM 检测 (dmesg)
  │                                     ├─ 死锁识别 (>15min 无文件变化)
  │                                     ├─ 信号诊断 (SIGSEGV/SIGKILL/SIGABRT)
  │                                     └─ 写入 .hpc_status.json
  │
  └─ check_calc.py (本地) ←── 下载输出文件 ←── 服务器
       --diagnose (深层分析收敛/几何问题)
```

## 首次部署

```
python <scripts_dir>/hpc_job.py upload --host <host> --port <port>
```

## 提交计算任务

```
python <scripts_dir>/hpc_job.py submit \
    --host <host> --code vasp \
    --dir /home/user/calc/Ni-111 \
    --cmd "mpirun -np 32 vasp_std" \
    --cores 32 --heartbeat 900 --walltime 86400
```

支持代码：`vasp` `cp2k` `lammps` `gaussian` `orca` `qe` `gromacs`

## 检查任务状态

```
python <scripts_dir>/hpc_job.py check --host <host> --dir /path --diagnose
python <scripts_dir>/hpc_job.py list --host <host>
python <scripts_dir>/hpc_job.py logs --host <host> --dir /path --tail 50
```

## 终止任务（强制审批）

```
# 第一步：查看状态（不带 --confirm，不会杀）
python <scripts_dir>/hpc_job.py kill --host <host> --dir /path

# 第二步：用户确认后
python <scripts_dir>/hpc_job.py kill --host <host> --dir /path --confirm
```

## 严禁行为

- **禁止** SSH 到服务器直接执行 `nohup mpirun ... &` 或 `vasp_std` 等
- **禁止** 绕过 hpc_watcher.py 直接用 `kill` 杀计算进程
- **禁止** 在未看到 hpc_job.py check 输出前，凭感觉判断"应该是跑完了"
- **禁止** 提交任务后不管不顾，必须告知用户如何 check 状态
- **禁止** 报错时盲目重试而不看 hpc_status.json 中的 `error_type` 和 `suggestion`

## 提交任务的标准工作流

```
1. 用 hpc_job.py submit 提交 → 获得 job_id 和初始状态
2. 告知用户：任务已提交，PID=xxx，用以下命令查看状态：
   python scripts/hpc_job.py check --host X --dir Y --diagnose
3. 用户询问进度时，用 hpc_job.py check + logs 查看
4. 如果任务失败：
   a. 查看 hpc_status.json 中的 error_type
   b. 根据诊断知识库确定修复方案
   c. 修改输入文件
   d. 用 hpc_job.py submit 重新提交
```

---

# 五大可靠性策略 — HPC 实施细则

## S1: Schema-Gated Execution

### Pre-flight Check Gate（提交前必检）

hpc_job.py submit 之前，必须对以下逐项检查，**全部通过才能提交**：

| 检查项 | VASP | CP2K | LAMMPS | Gaussian | ORCA |
|--------|------|------|--------|----------|------|
| 输入文件存在 | INCAR POSCAR POTCAR KPOINTS | .inp | in.* data.* | .gjf/.com | .inp |
| 原子重叠 | POSCAR 中任意原子对 >0.5Å | 同左 | 同左 | 同左 | 同左 |
| 参数合法性 | ENCUT≥200, EDIFF>0 | CUTOFF≥200 | timestep≤0.005 | %Mem≤90 | %maxcore>0 |
| 磁盘空间 | df -h 工作目录 ≥10GB | 同左 | 同左 | 同左 | 同左 |
| 核心数合理 | -np ≤ 服务器物理核心数 | 同左 | 同左 | %NProcShared | PAL≥1 |
| 无同名任务冲突 | remote_ps.py 检查无同名进程 | 同左 | 同左 | 同左 | 同左 |

**操作规则**：
1. 检查不通过 → 报告具体哪项失败 + 建议修改值 → 等用户确认 → 修改后再提交
2. 检查通过 → 直接提交，告知用户 pre-flight 已通过
3. **禁止跳过 pre-flight** 以"赶时间""应该没问题"为理由

### 修改门控

任何对远程服务器输入文件的修改：
1. 先用 scp 下载原文件到本地临时目录
2. 修改后用 diff 展示新旧差异（必须用 `diff -u` 格式）
3. 逐条说明每项修改的原因
4. 用户确认后再上传

## S2: Generator ≠ Reviewer

### HPC 操作中的实现

| 操作 | Generator（谁做） | Reviewer（谁审） |
|------|-------------------|-------------------|
| 生成 INCAR/KPOINTS | 主 Agent | 独立重读 POSCAR 后复核 K 点密度、ENCUT 合理性 |
| 写提交脚本 | 主 Agent | 检查 mpirun 参数、环境变量、路径是否正确 |
| 分析报错原因 | 主 Agent | 独立调用 check_calc.py 交叉验证诊断结论 |
| 修改输入参数 | 主 Agent | 逐项列出 old→new + reason，用户确认 |

### VERDICT 格式

每次审查末尾必须输出：
```
VERDICT: PASS — [通过原因]
VERDICT: FAIL — [失败原因] → [修复建议]
```

## S3: Context Engineering

### HPC 操作中的实现

1. **状态不靠记忆靠文件**：服务器状态永远从以下文件读取，不凭对话记忆：
   - `.hpc_status.json` — 计算任务状态
   - `remote_ps.py --json` — 进程清单
   - `check_calc.py --json` — 计算结果

2. **SSH 输出不上屏**：SSH 到服务器的任何裸输出（ps aux、cat log、ls）**禁止**直接粘贴到对话。必须：
   - 先下载到本地文件
   - 用解析器处理
   - 只报告解析结论

3. **日志片段策略**：需要展示日志时，仅展示与当前问题相关的关键行（≤50 行），前后用 `[...]` 标注省略。禁止全文粘贴。

4. **子代理隔离**：
   - 下载输出文件分析 → 独立 subagent
   - 修改输入文件 → 独立 subagent
   - 主 Agent 只看各 subagent 的 conclusion，不看完整过程

## S4: CodeAgents

### 结构化通信格式

所有 HPC 操作的参数修改和状态报告使用以下格式：

**参数修改报告**：
```json
{
  "file": "INCAR",
  "changes": [
    {"param": "ENCUT", "old": 400, "new": 350, "reason": "OOM: reduce memory by ~15%"},
    {"param": "ALGO", "old": "Normal", "new": "VeryFast", "reason": "Memory optimization for relaxation"}
  ],
  "expected_effect": "Memory reduction ~30%, speed +20%, accuracy change <1meV/atom"
}
```

**任务状态报告**：
```json
{
  "job_id": "Ni-111_12345_1717000000",
  "status": "running",
  "elapsed": "3h 25m",
  "output_size_mb": 234,
  "last_activity": "120s ago",
  "scf_cycles_completed": 15,
  "estimated_remaining": "~6h",
  "alerts": []
}
```

**提交命令构建**：每次 submit 必须显式列出所有参数，不用默认值隐式假设：
```
hpc_job.py submit \
  --host node01 --port 22 --user polestar \
  --code vasp --dir /home/polestar/calc/Ni-111 \
  --cmd "mpirun -np 32 vasp_std" \
  --heartbeat 900 --walltime 86400 --cores 32
```

## S5: Cognitive Firewalls

### HPC 专用防火墙

| 防火墙 | 触发条件 | HPC 场景动作 |
|--------|---------|-------------|
| **Hallucination Guard** | 打算建议修改 INCAR 标签值 | 先用 `grep` 确认该标签在 INCAR 中存在；建议的修改值必须在 VASP wiki/手册中有依据 |
| **Path Existence** | 引用服务器上的任何文件路径 | 先用 `test -f` 或 `ls` 通过 SSH 确认文件存在 |
| **PID Reality** | 说"PID 12345 的进程" | PID 必须来自 `remote_ps.py --json` 或 `.hpc_status.json`，不能来自记忆 |
| **Sunk-Cost Guardian** | 同一计算连续提交失败 ≥3 次 | 停。列出已尝试的修改 + 每次的报错。建议用户检查输入文件是否从根本上就有问题。禁止继续重试 |
| **Premature Closure** | 说"跑完了""修好了" | 检查：1) hpc_status.json 确认 status=completed 2) check_calc.py 确认结果合理 3) 是否正常结束（非 OOM/timeout） |
| **Command Injection** | 用户给的路径/参数包含 `;` `\|` `` ` `` `$()` 等 | 拒绝执行，询问用户意图 |

### 防火墙优先级

1. Command Injection > Hallucination Guard > Path Existence（安全第一）
2. Sunk-Cost Guardian > Premature Closure（防浪费 > 防遗漏）
3. 任何防火墙触发 → 先报告再等待，禁止越过

## S6: Success Capture（成功经验捕获）

### 触发条件

同一计算任务/同一类错误连续失败 **≥3 次**后，某方案**真正成功**（不是巧合通过，而是后续同类操作完全绕开了该坑）。

### "真正成功"的判定标准

| 假成功（不触发捕获） | 真成功（触发捕获） |
|---------------------|-------------------|
| 换了台服务器跑通了，但不知道原因 | 定位到是某 MPI 版本 bug，换版本后所有服务器都能跑 |
| 随机调参后某次过了 | 找到参数阈值（如 ENCUT<350 必 OOM），之后每次都避开 |
| 杀进程重跑后暂时好了 | 修了根因（如修了 ulimit、加了环境变量），之后不再复现 |
| 只跑通了一次，复现不了 | 方案可复现：同样的修改在同类计算上都有效 |

### 捕获工作流

```
同一问题失败 ≥3 次 → Sunk-Cost Guardian 触发 → 停止重试
  │
  ├─ 分析根因 + 找到方案 → 验证成功（真成功）
  │
  ├─ Step 1: 搜索现有规则文件
  │    grep -rl "<关键词>" comp-chem/ memory/
  │    找是否已有相关 md
  │
  ├─ Step 2: 判断归属
  │    ├─ 有匹配文件 → 报告："comp-chem/xxx.md 第 N 行有相关规则，建议追加"
  │    └─ 无匹配文件 → 报告："没有相关规则文件，建议新建 comp-chem/<topic>.md"
  │
  ├─ Step 3: 询问用户 → 等确认
  │
  └─ Step 4: 写入，格式如下：
```

### 写入模板

```markdown
## 问题：[一句话描述]

**识别特征**：[以后遇到什么症状就想到这条规则]

**失败历史**：
| 第 N 次 | 尝试方案 | 失败表现 | 学到什么 |
|---------|---------|---------|---------|
| 1 | [方案] | [错误] | [教训] |
| 2 | [方案] | [错误] | [教训] |
| 3 | [方案] | [错误] | [教训] |

**成功方案**：[具体步骤，可复现]

**为什么这次能绕开**：[根因分析]

**适用范围**：[哪些代码/场景适用，哪些不适用]
```

### 文件放置规则

| 问题范围 | 写入位置 |
|---------|---------|
| 仅涉及某个代码的参数调优 | `comp-chem/diagnostics.md` 对应代码段落 |
| 涉及 HPC/服务器/SSH 操作 | `comp-chem/hpc.md` 对应策略段落 |
| 跨代码的通用坑（如 MPI 版本） | `comp-chem/hpc.md` 环境初始化段落后 |
| 全新的独立主题 | 新建 `comp-chem/<topic>.md` + 在 CLAUDE.md 加触发词 |
| 与计算无关的经验 | `memory/<topic>.md` + 更新 MEMORY.md 索引 |

### 禁止行为

- **禁止** 成功后默默继续，不询问是否记录
- **禁止** 把假成功当真成功写入规则
- **禁止** 写入未经验证复现的方案
- **禁止** 把规则写在根 CLAUDE.md（根级只放触发条件）

## S7: Deep Retrospective（深度项目复盘）

### 触发条件

同一项目/任务在跨对话中连续失败，满足以下任一：
- Sunk-Cost Guardian 已停掉 ≥3 次重试，且 Success Capture 未产出真成功方案
- 同一服务器/代码/参数组合反复报同类错误
- 用户要求"深度分析""复盘""为什么总是失败"
- 换了服务器/参数/方法后问题依然复现 → 说明不是环境问题，是根因更深

### CCRM 原则（Context-Contaminated Restart Model）

**单纯重试失败的操作不会改善结果——上下文污染反而升高错误率。** 复盘必须从零重新审视假设，不带之前失败尝试的偏见。

### 三层复盘框架（来源：SAMULE, EMNLP 2025）

```
Level 1 — Micro（单次失败回顾）
  每次提交失败的完整参数快照
  → error_type + 尝试方案 + 输出特征

Level 2 — Meso（同任务跨尝试模式识别）
  对比同一项目下的所有失败记录
  → 共同模式？不同尝试之间的差异和共性？
  → 哪些参数始终没变过（可能是盲区）？

Level 3 — Macro（跨项目/跨代码的通用教训）  
  这个问题是否在其他体系/代码上也出现过？
  → 说明不是体系特异性问题，是方法论根因
```

### HPC 复盘检查表

**A. 环境假设验证**：
- [ ] 同一个计算在另一台同配置服务器上是否也失败？（排除单机故障）
- [ ] 不同 MPI 版本/编译器版本是否表现相同？（排除编译链 bug）
- [ ] 核心数减半后是否仍然失败？（排除并行 bug）
- [ ] 小体系（<20 原子）测试是否通过？（排除体系特异性）

**B. 输入文件根本审查**：
- [ ] POSCAR/初始构型：是否来自可靠来源？原子间距是否物理合理？
- [ ] POTCAR/赝势：版本是否正确？是否与泛函匹配？有无已知 bug？
- [ ] INCAR/参数：是否有冲突标签？是否有标签被静默忽略？
- [ ] KPOINTS：收敛测试是否做过？gamma-centered vs Monkhorst-Pack 是否正确？

**C. 方法论根本审查**：
- [ ] 选择的泛函/基组/赝势是否适合该化学体系？
- [ ] Slab/超胞模型：尺寸是否足够？真空层是否合理？偶极修正是否需要？
- [ ] 磁矩初始化：是否检查了文献中的磁基态？是否有多种可能磁序？
- [ ] 是否尝试过更保守/更激进的参数两端，而不仅仅是微调？

**D. 联网搜索**（关键一步）：
```
python <scripts_dir>/websearch.py "<体系/材料名> VASP convergence issues"
python <scripts_dir>/websearch.py "<错误关键词> computational chemistry troubleshooting"
```
搜索该体系是否有已知的计算难点、社区讨论、推荐参数。

### 复盘报告输出格式

```json
{
  "project": "Ni-111 surface adsorption",
  "failure_count": 5,
  "period": "2026-05-28 ~ 2026-06-06",
  "failures": [
    {"attempt": 1, "error_type": "oom_killed", "fix_tried": "reduce ENCUT 600→500", "result": "still OOM"},
    {"attempt": 2, "error_type": "oom_killed", "fix_tried": "reduce cores 64→32", "result": "still OOM"},
    {"attempt": 3, "error_type": "scf_diverged", "fix_tried": "ALGO=All", "result": "passed SCF but crashed in GEO_OPT"},
    "..."
  ],
  "pattern_analysis": {
    "common_theme": "OOM across all attempts despite reducing ENCUT and cores",
    "unchanged_params": ["KPOINTS (8x8x1)", "NCORE=1", "vacuum=25Å"],
    "blind_spot": "KPOINTS 8x8x1 for 2x2 surface → 16 k-points × 4 atoms may still be too many per core"
  },
  "root_cause_hypothesis": [
    {"hypothesis": "真空层 25Å 导致 FFT 网格过大", "evidence": "真空层占总晶胞体积 60%", "confidence": "HIGH"},
    {"hypothesis": "NCORE=1 导致每核复制全部波函数", "evidence": "32核 × 单核内存 = 总内存 32×", "confidence": "MEDIUM"}
  ],
  "recommended_new_approach": [
    "先压缩真空层到 15Å 做粗收敛 → 收敛后再扩展到 25Å",
    "NCORE=4 减少并行内存复制",
    "先用 1x1 表面小体系验证整套参数 → 再扩展到 2x2"
  ],
  "needs_web_search": true,
  "search_queries": ["Ni(111) VASP slab convergence vacuum thickness", "VASP NCORE memory scaling OOM"],
  "confidence": "MEDIUM"
}
```

### 复盘后行动铁律

1. **复盘后禁止直接动手** — 报告复盘结论 → 等用户确认 → 确认后才能执行
2. **一次只改一个根本假设** — 如果认为是真空层问题，先只改真空层测试，验证通过后再调其他参数
3. **新方案必须做小体系预验证** — 用最小可行体系（1x1 表面/最小 k 点）跑通再扩展到目标体系
4. **每个新尝试必须在复盘框架中记录** — 保持 Meso 层的数据积累
