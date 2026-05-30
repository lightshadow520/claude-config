# HPC 与远程服务器操作规则

本文件在 CLAUDE.md 触发关键词匹配时加载，覆盖 SSH 诊断、进程管理、计算任务提交。

---

# SSH 连接诊断规则

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
