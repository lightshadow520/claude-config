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

**AutoDL/GPUshare 等代理网关平台**：SSH 连接走的是代理网关（如 `connect.xxx.seetacloud.com`），不是直接连实例。网关有独立的空闲超时——几分钟不传数据就断开。**网页终端不经过 SSH 代理，所以不会断。**

**所有连接函数已内置 keepalive（30s 心跳）：**
- paramiko: `transport.set_keepalive(30)`（在 `client.connect()` 之后）
- 原生 SSH: `-o ServerAliveInterval=30 -o ServerAliveCountMax=3`
- 覆盖：`remote_ps.py`、`hpc_job.py`（ssh_cmd/scp_upload/scp_download）

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

# AutoDL / Docker 环境 MPI 多进程方案

本段覆盖 AutoDL、GPUshare 等 Docker 容器平台的 MPI 并行计算问题。

## 核心问题：OpenMPI + Docker = X11 探测死锁

**症状**：`mpirun` 永远挂死，不产生任何输出，进程停留在 S 状态（interruptible sleep）。即使用 `timeout` + SIGKILL 也杀不掉。

**根因**：OpenMPI 的 `orted` 守护进程启动时会遍历 X11 端口（6000-6063，对应 DISPLAY :0 到 :63），**无论 DISPLAY 环境变量是否设置**。AutoDL 等平台的 Docker 容器通过 NAT 规则将某些 X11 端口（如 6007）转发到宿主机的 VNC Server。VNC 接受 TCP 连接但不响应 X11 协议握手，导致 `orted` 在 `poll()` 中永久等待。

**诊断方法**（在服务器上执行）：
```bash
# 1. 确认 MPI 实现类型
mpirun --version 2>&1 | head -2
# 输出含 "HYDRA" → MPICH（无此问题）
# 输出含 "Open MPI" / "orted" → OpenMPI（可能受影响）

# 2. 如为 OpenMPI，strace 确认是否卡在 X11 端口
timeout 3 strace -f mpirun --allow-run-as-root -np 1 hostname 2>&1 | grep -E "connect.*600[0-9]|poll.*POLLIN"
# 看到 connect() 成功 + poll() 不返回 → 确认 X11 死锁

# 3. 确认 Docker 环境
test -f /.dockerenv && echo "Docker 容器" || echo "非 Docker"
cat /proc/1/cgroup | head -1
```

## 推荐方案：换用 MPICH（首选）

MPICH 的 Hydra 进程管理器用 `fork()+exec()` 直接启动进程，不走 X11 探测。AutoDL 上已验证通过。

```bash
# 安装 MPICH（替换 OpenMPI）
apt install mpich

# 验证
mpirun -np 4 hostname          # 应秒过
mpirun -np 30 vasp_std         # VASP 多进程并行
```

**注意**：MPICH 不需要 `--allow-run-as-root` 参数。如果之前用 OpenMPI 的 `vasp_std` 二进制，需要重新编译链接 MPICH。

## 备选方案：OpenMPI + LD_PRELOAD 拦截（不改 MPI 实现）

如果不能/不想换 MPICH，用 `block_x11.so` 拦截 X11 端口连接。

脚本位置：`C:\Users\polestar\.claude\scripts\block_x11.c`

```bash
# 1. 上传并编译（服务器上）
gcc -shared -fPIC -o /tmp/block_x11.so block_x11.c -ldl

# 2. 使用
LD_PRELOAD=/tmp/block_x11.so mpirun --allow-run-as-root -np 30 vasp_std

# 3. 或写入 run_vasp.sh
export LD_PRELOAD=/tmp/block_x11.so
mpirun --allow-run-as-root -np $NPROCS vasp_std
```

**原理**：拦截对 `127.0.0.1:6000-6063` 的 `connect()` 调用，直接返回 `ECONNREFUSED`。orted 探测一圈全被拒，100ms 内跳过，继续正常 MPI 初始化。

## 提交前检查清单（AutoLDocker 环境）

**铁律：每次通过 SSH 连接到远程服务器，提交任何计算之前，必须先跑以下环境探测。
不论用户是否提到 Docker/AutoDL/MPI —— 只要走了 SSH 连接，这一条就自动触发。**

```
# 第一步：环境探测（SSH 连接后立即执行，不依赖用户关键词）
[ ] cat /proc/1/cgroup | head -1          # 确认容器类型
[ ] test -f /.dockerenv && echo "Docker" || echo "非Docker"
[ ] mpirun --version 2>&1 | head -2       # 确认 MPI 实现（OpenMPI vs MPICH）
[ ] df -h /dev/shm                         # 共享内存大小
[ ] ulimit -s                              # 栈空间（需 unlimited）

# 第二步：MPI 可用性验证
[ ] mpirun -np 1 hostname                  # 单进程 MPI 能跑
[ ] mpirun -np 4 hostname                  # 多进程 MPI 能跑

# 第三步：代码二进制验证
[ ] vasp_std 能启动并输出 "No INCAR found"（或对应代码的等效测试）

# 第四步：如果任何一步失败 → 立即查 error_db.json
python <scripts_dir>/query_errors.py --search "<失败症状>"
```

**Docker + OpenMPI 组合 → 立即预判 X11 死锁**：检查清单中 `mpirun -np 1 hostname` 挂死 + Docker 环境 + OpenMPI → 直接走 LD_PRELOAD 方案，不要浪费时间试 MCA 参数。

### 经验 2026-06-08：MPICH 可能在部分 AutoDL 实例上也失败

**识别特征**：`apt install mpich` 后 `mpiexec -np 1 hostname` 秒过，但 `mpiexec -np 1 vasp_std` 挂死，进程全在 Ss 状态。`hydra_pmi_proxy` 进程参数中显示 `--launcher ssh` 而非 `--launcher fork`。

| 第 N 次 | 尝试方案 | 失败表现 | 学到什么 |
|---------|---------|---------|---------|
| 1 | 换 MPICH（apt 安装）| `hostname` 能跑但 `mpitest`(调用 MPI_Init)挂 | MPICH Hydra 默认在某些 Docker 上用 SSH launcher |
| 2 | 显式 `-launcher fork` | 仍挂，hydra_pmi_proxy 用了 fork 但 PMI 握手失败 | PMI 握手也有问题，不是仅 X11 |
| 3 | Intel MPI mpirun 跑 MPICH 编译的二进制 | 进程被 timeout 杀，无输出 | SONAME 不兼容(libmpich.so.12 vs libmpi.so.12) |
| 4 | 重回 OpenMPI + LD_PRELOAD | **成功**，30 核 VASP 全速跑 | block_x11.so 是最可靠的兜底方案 |

**成功方案**（当 MPICH 也失败时）：

```bash
# 1. 上传并编译 block_x11.so
gcc -shared -fPIC -o /tmp/block_x11.so block_x11.c -ldl

# 2. 编译 VASP 时注意去掉 -DHOST 定义（避免 shell 引号问题）
# makefile.include 中 CPP_OPTIONS 不加 -DHOST

# 3. run_vasp.sh
export LD_PRELOAD=/tmp/block_x11.so
ulimit -s unlimited
export OMP_NUM_THREADS=1
mpirun.openmpi --allow-run-as-root -np $NPROCS vasp_std
```

**适用范围**：Docker 容器 + 任何 MPI 实现都失败时，OpenMPI + LD_PRELOAD 是最终兜底。

### 经验 2026-06-08：Docker 容器内进程清理

**识别特征**：`killall -9 vasp_std` 不报错但进程全部残留，`ps aux` 显示进程仍在 Ss/Rl 状态。

**根因**：`killall` 在 Docker 容器内匹配进程名时可能因路径差异失败；多次失败重试累积大量僵尸进程（本案例累积 124 个）。

**正确清理方法**：用 paramiko 逐 PID 发 `kill -9`，绕过 shell 转义问题：

```python
# 不要用 shell 管道，逐 PID 发信号
stdin, stdout, stderr = ssh.exec_command('ps -eo pid,comm --no-headers | grep -E "vasp|mpirun|orted"', timeout=10)
for line in stdout.read().decode().strip().split('\n'):
    pid = line.strip().split()[0]
    ssh.exec_command(f'kill -9 {pid} 2>/dev/null', timeout=3)
```

**警告**：多个 mpirun 实例同时写同一工作目录会互相覆盖 OUTCAR/OSZICAR。重启前必须确认旧进程已全部清理。

---

# 远程服务器进程管理（强制规则）

对远程 Linux 服务器执行任何进程操作前，**必须先用 `remote_ps.py` 获取结构化进程清单**。

**禁止直接 SSH 执行 `ps aux` 然后人工分析输出。** 原始 `ps aux` 输出在上下文窗口中极易导致：
- 遗漏僵尸进程（混在正常输出中不可见）
- 误判进程归属（多用户/多任务时看不清谁是谁）
- 上下文爆炸（200+ 行进程列表吞噬 token 预算）

## 查看进程

```
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host>                        # 结构化概览
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host> --diagnose             # 概览 + 自动诊断
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host> --json                 # 结构化 JSON
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host> --port <port> --user <user>
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host> --method ssh           # 用系统 SSH
python C:\Users\polestar\.claude\scripts\remote_ps.py --host <host> --timeout 60           # 长超时
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
python C:\Users\polestar\.claude\scripts\hpc_job.py upload --host <host> --port <port>
```

## 提交计算任务

```
python C:\Users\polestar\.claude\scripts\hpc_job.py submit \
    --host <host> --code vasp \
    --dir /home/user/calc/Ni-111 \
    --cmd "mpirun -np 32 vasp_std" \
    --cores 32 --heartbeat 900 --walltime 86400
```

支持代码：`vasp` `cp2k` `lammps` `gaussian` `orca` `qe` `gromacs`

## 检查任务状态

```
python C:\Users\polestar\.claude\scripts\hpc_job.py check --host <host> --dir /path --diagnose
python C:\Users\polestar\.claude\scripts\hpc_job.py list --host <host>
python C:\Users\polestar\.claude\scripts\hpc_job.py logs --host <host> --dir /path --tail 50
```

## 终止任务（强制审批）

```
# 第一步：查看状态（不带 --confirm，不会杀）
python C:\Users\polestar\.claude\scripts\hpc_job.py kill --host <host> --dir /path

# 第二步：用户确认后
python C:\Users\polestar\.claude\scripts\hpc_job.py kill --host <host> --dir /path --confirm
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
  └─ Step 4: 写入，优先写入结构化数据库
```

### 写入目标优先级

**铁律：结构化数据库 > MD 文件。先写 `error_db.json`，需要详细叙述时再补 MD。**

| 优先级 | 目标 | 何时用 |
|--------|------|--------|
| **1st** | `comp-chem/error_db.json` | 所有计算报错、HPC 环境坑、进程管理问题 → 追加新 error_type 或扩展现有条目 |
| 2nd | `comp-chem/hpc.md` 对应段落 | 需要详细诊断步骤、命令示例、较长说明时补充 |
| 3rd | `memory/<topic>.md` | 与计算无关的跨领域通用教训 |

### error_db.json 写入格式

```json
{
  "error_type": "<snake_case>",
  "severity": "critical|warning|info",
  "symptoms": ["<可 grep 的特征>"],
  "diagnostic_checks": ["<确认命令>"],
  "root_causes": [{"cause": "...", "likelihood": "high|medium|low"}],
  "fixes": [{
    "action": "<一句话>",
    "params": {"PARAM": "value"},
    "confidence": "HIGH|MEDIUM|LOW",
    "applies_to": ["vasp","cp2k",...],
    "side_effects": "...",
    "validation": "..."
  }],
  "failure_history": [
    {"attempt": 1, "solution": "...", "result": "...", "lesson": "..."}
  ],
  "cross_references": ["<相关 error_type>"],
  "source": "<日期 + 服务器>"
}
```

### MD 补充格式（仅在需要详细叙述时用）

```markdown
**识别特征**：[以后遇到什么症状就想到这条规则]

**失败历史**：
| 第 N 次 | 尝试方案 | 失败表现 | 学到什么 |
|---------|---------|---------|---------|
| 1 | [方案] | [错误] | [教训] |

**成功方案**：[具体步骤，可复现]
**为什么这次能绕开**：[根因分析]
**适用范围**：[哪些代码/场景适用，哪些不适用]
```

### 禁止行为

- **禁止** 成功后默默继续，不询问是否记录
- **禁止** 把假成功当真成功写入规则
- **禁止** 写入未经验证复现的方案
- **禁止** 把规则写在根 CLAUDE.md（根级只放触发条件）
- **禁止** 只写 MD 不写 error_db.json（结构化数据库是主数据源，MD 是补充）

## S7: Deep Retrospective（深度项目复盘）

**通用框架见** `C:\Users\polestar\.claude\deep-retrospect.md`。
首次触发时先加载通用框架，再回到本文件查看 HPC/服务器 特有补充。

### HPC/服务器领域特有检查项

在完成通用检查表（根本假设审查 A-E）的基础上，补充以下：

**环境假设验证**：
- [ ] 同一个计算在另一台同配置服务器上是否也失败？（排除单机故障）
- [ ] 不同 MPI 版本/编译器版本是否表现相同？（排除编译链 bug）
- [ ] 核心数减半后是否仍然失败？（排除并行 bug）
- [ ] 小体系（<20 原子）测试是否通过？（排除体系特异性）
- [ ] SSH 连接是否稳定？是否因 CPU 满载导致超时误判？

**远程操作审计**：
- [ ] 是否有 `remote_ps.py` 记录佐证每次失败时的服务器负载状态？
- [ ] 是否有 `.hpc_status.json` 记录佐证每次的完整 error_type？
- [ ] 每次失败后是否验证过进程已完全清理（无僵尸进程残留）？
- [ ] 输入文件是否每次都是从本地经过 pre-flight check 后上传的（而非直接在服务器上修改）？

**联网搜索（HPC 专项）**：
```
python C:\Users\polestar\.claude\scripts\websearch.py "<代码名> <error_type> known fix server environment"
python C:\Users\polestar\.claude\scripts\websearch.py "MPI <版本> <代码名> bug crash"
```
