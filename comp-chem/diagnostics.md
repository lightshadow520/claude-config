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
