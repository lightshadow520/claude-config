# 计算化学排错与输出解析

本文件在 CLAUDE.md 触发关键词匹配时加载，覆盖输出解析规则和分代码排错知识库。

---

# 输出解析（强制规则）

遇到以下任何场景，**必须先跑解析器再回答，无论文件在本地还是远程服务器**。

## 触发关键词

- 还要多久 / 什么时候跑完 / 预估时间 / 还要多少步 / 还剩多少
- 收敛了吗 / 收敛得怎么样 / 能量收敛 / 收敛情况
- 为什么报错 / 出了什么问题 / 这个错误什么意思 / 跑失败了 / 失败了
- 进度如何 / 跑得怎么样了 / 看看结果 / 检查计算
- 帮我看看这个输出 / 分析这个 log / OUTCAR / OSZICAR / .out / .log
- 服务器上的计算 / ssh / 远程 / 看看跑完没

## 本地文件

```
python <scripts_dir>/check_calc.py <文件路径>              # 查进度
python <scripts_dir>/check_calc.py <文件路径> --diagnose   # 报错场景
python <scripts_dir>/check_calc.py <文件路径> --json       # 需要精确数据
```

## 远程服务器文件（强制四步，不可跳过）

1. 用 paramiko/SSH 连服务器，找到输出文件路径
2. 用 sftp/scp 下载输出文件到本地临时目录
3. 跑 `python <scripts_dir>/check_calc.py <本地临时文件> --diagnose`
4. 根据解析结果回复

**严禁直接用 Read 读原始输出文件来回答上述问题。**
**严禁 SSH 到服务器 cat/tail 输出然后自己分析。**
**严禁凭进程 CPU 占用/运行时间猜测还要多久。**

## 排查流程

脚本诊断置信度为 HIGH → 直接按修复建议执行。
脚本诊断不明确 → 读 `<config_dir>/comp-chem-sop.md`，按 1→6 步排查：
原子坐标 → SCF 收敛 → 几何优化 → 资源/环境 → 输入文件 → 并行/环境

## 支持的代码
VASP、ORCA、CP2K、LAMMPS、GROMACS、AMBER、Gaussian、Materials Studio、ML potentials

## 无需触发的话题
方法选择建议、行业讨论、代算业务、数据存储管理 —— 正常回答即可

---

# 排错专家知识库

接到计算失败报告时，按以下决策树处理。

## 第一步：读 error_type

`hpc_status.json` 中的 `error_type` 字段直接告诉你发生了什么：

| error_type | 含义 | 优先排查 |
|------------|------|----------|
| `oom_killed` | 内存不足被系统 OOM Killer 杀掉 | 降低内存需求 |
| `Deadlock_Timeout` | 进程未退出但输出文件停止更新 | 死锁/FFT爆炸/MPI挂死 |
| `segfault` | 段错误 (SIGSEGV) | 栈溢出/内存越界/输入错误 |
| `aborted` | 断言失败 (SIGABRT) | 输入参数不合法 |
| `terminated` | 被终止 (SIGTERM) | 队列墙时间/手动终止 |
| `killed_by_signal` | 被信号杀死（非 OOM） | 检查具体信号 |
| `timeout` | 超过 walltime | 增加时间或减小体系 |
| `generic_error` | exit code 1 | 直接看 OUTCAR/log 末尾 |

## 第二步：按代码排错

### VASP

**OOM →**
- 降低 `ENCUT`（尝试 400→350）
- `ALGO = VeryFast`（减少内存占用 ~30%）
- 调整 `NCORE`（=总核数，最小化并行内存复制）
- 减少 K 点数量（用 `KSPACING` 代替 KPOINTS 文件）

**Deadlock / FEWALD 卡死 →**
- 真空层过大导致 FFT 网格爆炸 → 检查 POSCAR 真空层是否 >20Å，收窄真空层
- 设置 `LREAL = Auto`
- 减小 `PREC` 为 Normal
- 检查 MPI 共享内存：设置 `export I_MPI_SHM_LMT=shm`

**SIGSEGV →**
- 必须先设置 `ulimit -s unlimited`
- 栈溢出：用 `OMP_STACKSIZE=512M`
- 内存越界：降低 `ENCUT` 或 `NGX/NGY/NGZ`
- 检查 POSCAR 中是否有原子重叠（<0.5Å）

**SCF 不收敛 →**
- `ALGO = All`（比 Normal/Damped 更稳定）
- `AMIX = 0.2; BMIX = 1.0`（更保守的电荷混合）
- `ISMEAR = 0; SIGMA = 0.05`（金属体系用 1，SIGMA=0.1）
- `LDIAG = .TRUE.` 确保使用对角化而不是 Davidson

### CP2K

**OOM →**
- 降低 `CUTOFF` 和 `REL_CUTOFF`
- 减少 `MAX_SCF` 迭代次数
- 使用 OT 代替对角化（`RUN_TYPE ENERGY` 等）

**SCF 不收敛 →**
- 从对角化切换到 OT：
  ```
  &SCF
    SCF_GUESS RESTART
    EPS_SCF 1.0E-6
    MAX_SCF 200
    &OT ON
      MINIMIZER DIIS
      PRECONDITIONER FULL_SINGLE_INVERSE
    &END OT
  &END SCF
  ```
- 用 `SMEARING` 方法替代 `FERMI_DIRAC`

### LAMMPS

**Lost atoms →**
- 减小 timestep（`timestep 0.0005` 而非 `0.001`）
- 放宽 shake tolerance：`fix ... shake 0.0001 20 0 b ...`
- 增加邻居列表重建频率：`neigh_modify every 1 delay 0 check yes`
- 检查初始构型中是否有原子重叠

**OOM →**
- 减小 cutoff：在 pair_style 中减小截断半径
- 减少处理器网格维度
- 使用 `processors * * *` 优化并行布局

**Segfault →**
- 检查 pair_style 和 pair_coeff 参数是否匹配
- 确认势函数文件路径正确
- 重新编译带有 debug flag

### Gaussian

**Convergence failure →**
- `SCF=QC`（二次收敛，最稳定但最慢）
- `SCF=NoVarAcc` + `scf=conver=6`
- `int=ultrafine` 提高积分精度

**Link 9999 →**
- 几何优化失败
- `opt=calcfc`（计算力常数重新开始）
- `opt=cartesian` 切换到笛卡尔坐标
- 检查初始构型是否合理

**Segfault →**
- 减小 `%Mem`（当前值减少 20%）
- 检查 `%chk` 路径和磁盘空间
- `scf=novaracc` 减少内存分配高峰

### ORCA

**SCF 循环不收敛 →**
- `SlowConv` 关键词
- `SCFConvForced` 强制进入下一阶段
- 提高 `grid` 到 `Grid5` 或 `Grid6`
- 尝试 `! UKS` 而不是 `! RKS`（允许自旋污染）

**内存不足 →**
- `%maxcore` 降低（单位 MB per core）
- `RIJCOSX` 代替 `RI`（减少内存）
- 降低基组尺寸

## 第三步：通用排错

以上两步未解决时，读 `<config_dir>/comp-chem-sop.md` 的 1→6 步排查流程。

## 环境初始化（hpc_watcher.py 自动执行）

每个代码提交时会自动设置以下环境——如果手动调试，先执行这些：

```bash
ulimit -s unlimited           # VASP/CP2K 栈溢出头号杀手
ulimit -c 0                  # 禁止 core dump
export OMP_NUM_THREADS=1     # 防止 OpenMP 与 MPI 冲突死锁
export I_MPI_SHM_LMT=shm     # Intel MPI 大体系共享内存
```

---

# 五大可靠性策略 — 排错实施细则

## S1: Schema-Gated Execution

### 诊断决策树（必须按顺序，禁止跳步）

```
报错/失败报告
  │
  ├─ Step 0: 确认信息来源
  │    ├─ 来源 = hpc_status.json → 继续
  │    ├─ 来源 = check_calc.py --json → 继续
  │    └─ 来源 = "我感觉"/"上次也是这样"/凭记忆 → 停！先跑解析器
  │
  ├─ Step 1: 读取 error_type（diagnostics.md 表 1）
  │    └─ error_type 未知 → 下载输出文件 → check_calc.py --diagnose
  │
  ├─ Step 2: 确定修复方案（diagnostics.md 表 2: 按代码排错）
  │    └─ 表中无匹配 → comp-chem-sop.md 1→6 步排查
  │
  └─ Step 3: 改参数 → 展示 diff → 等确认 → 重新提交
```

### 修改参数前的强制校验

每次建议修改输入参数，必须通过以下检查：

| 检查 | 规则 |
|------|------|
| 标签存在性 | 建议改 ENCUT？先 grep INCAR 确认 ENCUT 标签存在 |
| 值域合法性 | ENCUT 不能 <100 或 >1500；EDIFF 必须 >0 且 <1E-2 |
| 参数兼容性 | ALGO=All 与 LDIAG=.FALSE. 冲突 → 必须提醒 |
| 物理合理性 | 真空层从 20Å 改为 5Å → 必须警告"可能引入层间相互作用" |
| 来源可溯 | 建议值来自 Wiki/手册/已验证的计算 → 标注来源 |

**违规示例**：
- ❌ "把 ENCUT 降到 300 试试" — 没确认 ENCUT 当前值，没确认 300 是否合法
- ✓ "INCAR 当前 ENCUT=400，OOM 报错。建议降至 350（VASP wiki 推荐 ≥max(ENMAX)×1.3，当前 POTCAR ENMAX=271，350≥352 ✓）"

## S2: Generator ≠ Reviewer

### 排错中的实现

| 步骤 | 角色 |
|------|------|
| 读 hpc_status.json + 输出文件 | 数据收集（只读） |
| 判断 error_type + 定位问题参数 | 诊断（Generator） |
| 用 check_calc.py 独立复核诊断结论 | 审查（Reviewer） |
| 两个诊断结论一致 → 报告方案 | 通过 |
| 两个诊断结论不一致 → 标注分歧，两个方案都报告给用户 | 升级 |

### 诊断分歧时的输出格式

```
⚠ 诊断存在分歧：
  [Agent 判断]: FEWALD 死锁 → 建议收窄真空层
  [check_calc.py]: SCF 电子步不收敛 → 建议 ALGO=All + AMIX=0.2
  [综合建议]: 先修复 SCF 收敛（基础问题），收敛通过后如再遇 FEWALD 再调真空层
```

## S3: Context Engineering

### 排错中的实现

1. **输出文件不全文加载**：
   - OUTCAR >10MB → 只用 `tail` 取最后 200 行 + `grep` 关键词行
   - OSZICAR 只取最后 50 行 + 关键的 F= 行
   - 用 `check_calc.py` 提取结构化信息代替人工读文件

2. **错误信息折叠**：
   - 同类型错误重复出现 → 报告"出现了 N 次"，只展示首末各 1 例
   - 堆栈跟踪 → 只截取包含用户代码路径的行，系统级帧省略

3. **诊断结论压缩**：每次诊断完毕后，主 Agent 只保留：
   - error_type（1 行）
   - 根因分析（≤3 行）
   - 修复建议（≤3 行）
   - 完整输出转存到本地文件，用路径引用

## S4: CodeAgents

### 排错通信格式

**错误诊断报告**（每次诊断必须输出此格式）：
```json
{
  "error_type": "oom_killed",
  "evidence": [
    "hpc_status.json: exit_code=-9, error_type=oom_killed",
    "dmesg: 'Out of memory: Killed process 12345 (vasp_std)'",
    "OUTCAR final line: maximum memory used: 47.2 GB"
  ],
  "root_cause": "ENCUT=600 + 32核导致每核内存需求超过节点限制(2GB/core)",
  "fix": [
    {"action": "reduce", "param": "ENCUT", "from": 600, "to": 450, "reason": "降低平面波基组"},
    {"action": "set", "param": "NCORE", "value": 4, "reason": "减少内存复制"}
  ],
  "confidence": "HIGH",
  "cross_validated": true,
  "cross_validated_by": "check_calc.py --diagnose"
}
```

### 禁止的通信方式

- ❌ "感觉是 OOM，把 ENCUT 降一下吧" — 无证据、无具体值、无验证
- ❌ "改了几个参数你跑跑看" — 没说哪个参数、改成多少
- ❌ 大段 OUTCAR 原文粘贴 — 用 check_calc.py 提取

## S5: Cognitive Firewalls — 排错专用

### 诊断专用防火墙

| 防火墙 | 触发条件 | 排错场景动作 |
|--------|---------|-------------|
| **Evidence Gate** | 打算说"原因应该是 X" | 必须先列出支持 X 的**至少 2 条**来自输出文件/status 文件的具体证据。无证据 → 说"不确定，需要进一步检查" |
| **Single-Change Rule** | 打算一次性修改 ≥3 个参数 | 停。每次最多改 2 个参数。原因：改 5 个参数跑通了无法知道哪个起效。必须告知用户"先验证这 2 个改动的效果" |
| **Regression Check** | 建议修改值是之前试过且失败的 | 立即警告："此值在 [某次提交] 中已尝试且失败，不建议重复" |
| **Wiki Citation** | 声称"VASP wiki 说"或"官方建议" | 必须在对话中引用具体的 Wiki 页面路径或参数说明文字，不能凭空 |
| **Confidence Label** | 每次给出诊断结论时 | 必须标注 `[确信]` / `[大概率]` / `[待验证]`。`[待验证]` 的结论必须建议用户如何验证 |
| **No-Guess Time** | 用户问"还要多久"/"什么时候跑完" | **禁止**凭感觉估算。必须用 check_calc.py 从 OUTCAR/OSZICAR 提取实际迭代进度计算 ETA |

### 违反后果

任何防火墙触发时：
1. 报告触发了哪个防火墙
2. 说明为什么触发（具体违反了哪条规则）
3. 提供符合规则的替代方案
4. 等用户确认后继续
