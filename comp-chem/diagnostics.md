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
python C:\Users\polestar\.claude\scripts\check_calc.py <文件路径>              # 查进度
python C:\Users\polestar\.claude\scripts\check_calc.py <文件路径> --diagnose   # 报错场景
python C:\Users\polestar\.claude\scripts\check_calc.py <文件路径> --json       # 需要精确数据
```

## 远程服务器文件（强制四步，不可跳过）

1. 用 paramiko/SSH 连服务器，找到输出文件路径
2. 用 sftp/scp 下载输出文件到本地临时目录
3. 跑 `python C:\Users\polestar\.claude\scripts\check_calc.py <本地临时文件> --diagnose`
4. 根据解析结果回复

**严禁直接用 Read 读原始输出文件来回答上述问题。**
**严禁 SSH 到服务器 cat/tail 输出然后自己分析。**
**严禁凭进程 CPU 占用/运行时间猜测还要多久。**

## 排查流程

脚本诊断置信度为 HIGH → 直接按修复建议执行。
脚本诊断不明确 → 读 `C:\Users\polestar\.claude\comp-chem-sop.md`，按 1→6 步排查：
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
| `scf_diverged` | SCF 迭代发散（电子步能量不降反升） | 立即切换混合参数/算法 |
| `scf_stagnant` | SCF 迭代停滞（dE 不再缩小但不收敛） | 混合参数/预条件器/算法 |
| `scf_oscillating` | SCF 迭代震荡（能量反复跳动不衰减） | 电荷晃动→线性混合→Kerker |
| `generic_error` | exit code 1 | 直接看 OUTCAR/log 末尾 |

## 第一步半：实时收敛监控（强制）

**提交计算后必须周期性检查 OSZICAR/OUTCAR 的 SCF 收敛趋势，不能只等最终结果。**

### 监控指标（从 OUTCAR/OSZICAR 提取）

| 指标 | VASP 来源 | CP2K 来源 | 含义 |
|------|----------|----------|------|
| dE（相邻电子步能量差） | OSZICAR 每行第 2 列 | cp2k.out `Energy change` | 越小越接近收敛 |
| dE 趋势（最近 10 步斜率） | 线性拟合 | 同左 | >0 → 发散；<0 但平 → 停滞 |
| dE 震荡幅度（最近 10 步 StdDev） | 标准差 | 同左 | >0.1 Ha → 严重震荡 |
| 收敛率（-log₁₀(dE) vs 步数） | 半对数图斜率 | 同左 | <0.02/步 → 极慢，需要干预 |
| SCF 步数/总预算 | N/TOTAL (OSZICAR) | SCF step N/MAX_SCF | >80% 用尽 → 几乎一定失败 |

### 干预阈值（任一触发即介入）

```
🔴 立即干预（别再浪费核心小时）：
  ├─ dE 最近10步单调递增 → SCF 发散，立刻停
  ├─ dE 震荡幅度 >0.1 Ha 且不衰减 → 电荷晃动，线性混合
  └─ SCF 步数 >80% NELM/MAX_SCF 且 dE > 10× EPS_SCF → 必然失败

🟡 预警（标记，下一轮未改善再干预）：
  ├─ dE 最近10步持平（斜率绝对值 < 0.001 Ha/步）→ 停滞
  ├─ dE 最近10步 StdDev 在扩大的震荡 → 混合参数可能恶化
  └─ 收敛率 <0.02/步 → 进展太慢

🟢 正常：
  └─ dE 单调递减 + 震荡衰减 → 继续等
```

### 监控频率

| 计算阶段 | 检查频率 |
|---------|---------|
| 提交后前 30 步 SCF | 每 10 分钟检查一次 |
| SCF 稳定收敛中 | 每 30 分钟检查一次 |
| 接近收敛（dE < 100× EPS_SCF） | 每 15 分钟检查一次 |
| 几何优化阶段（非电子收敛） | 每 1-2 小时检查一次 |

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

**SCF 不收敛 → 五级救援协议**（来源：VASP wiki + Marsman 讲座 + Custodian + Materials Project 验证）

**收敛前分析（OUTCAR GAMMA 特征值）：**
OUTCAR 每次电子步输出电荷介电矩阵特征值谱。GAMMA 均值 ~1 是最优。
`AMIX_optimal = AMIX_current / GAMMA_mean`。特征值宽度越大 → 电荷混合越不稳定。

```
Level 1：保守混合（不改算法）
  ICHARG = 12（一次性非自洽步，不更新电荷密度，获取轨道）
  → 跑完后 ICHARG = 2 + AMIX = 0.1 + BMIX = 0.01
  → 收敛后逐步增大 BMIX 提速
  
Level 2：线性混合（针对电荷晃动/slab/表面体系）
  AMIX = 0.05 + BMIX = 0.0001（接近线性混合）
  MAXMIX = 10-20（减少 Pulay 混合记忆步数，默认-45）
  → 对 slab/真空/带电体系尤其有效

Level 3：切换算法
  绝缘体/小带隙 → ALGO = All（band-by-band CG，最稳定）
  金属 → ALGO = Fast 或 VeryFast（RMM-DIIS）
  金属+磁矩复杂 → ALGO = Damped + TIME = 0.4

Level 4：改电子结构设置
  ISMEAR 策略：
    - 半导体/绝缘体 → ISMEAR = 0, SIGMA = 0.05
    - 金属 → ISMEAR = 1, SIGMA = 0.1
    - 带隙<0.1eV → ISMEAR = -5 (tetrahedron+Blochl，禁止配合 ALGO=All/Damped)
  注意：ISMEAR < 0 禁止与 ALGO in [All, Damped] 同用（Custodian 强制拦截）

Level 5：磁矩专项
  AMIX_MAG = 0.4-0.8（磁矩密度混合，默认偏激进）
  BMIX_MAG = 0.0001（极弱混合保收敛）
  MAGMOM 设置到物理合理初始值
  预收敛非磁性 → 拷贝 WAVECAR → 打开 ISPIN=2 重启
  f 电子体系：AMIX_MAG = 0.8, BMIX_MAG = 0.00001 + L(S)DA+U (U=3-7eV)
```

**HSE 杂化泛函专项：**
```
1. 先用 PBE 预收敛，拷贝 WAVECAR + CHGCAR
2. ALGO = Damped（变分总能量必需），TIME = 0.5
3. VASP 6 默认启用 ACE（自适应压缩交换），比 VASP 5 快 ~3 倍
4. 仍不收敛 → ALGO = All + 降低 ENCUT 20% → 收敛后读 WAVECAR 回到高 ENCUT
```

**Custodian 的生产级修复逻辑**（Materials Project >10 万次计算验证，成功率 >98%）：
`VaspErrorHandler` 按优先级依次尝试：AMIX/BMIX 调节 → ALGO 降级（VeryFast → Fast → Normal → Damped）→ WAVECAR 删除（怀疑被写坏）→ 停机报错

### CP2K

**OOM →**
- 降低 `CUTOFF` 和 `REL_CUTOFF`
- 减少 `MAX_SCF` 迭代次数
- 使用 OT 代替对角化（`RUN_TYPE ENERGY` 等）

**SCF 不收敛 → 先判断体系类型再选方案**

**OT 适用性判定**（来源：CP2K 官方文档 + pymatgen）：
```
体系有带隙 >0.5eV？
├─ YES → 使用 OT（快且鲁棒）
│   ├─ 正常收敛 → FULL_KINETIC + DIIS
│   ├─ 收敛困难 → FULL_SINGLE_INVERSE + CG
│   └─ 仍失败 → FULL_ALL + ENERGY_GAP <gap_estimate> + CG
└─ NO（金属/零带隙/电荷晃动）→ 对角化 + smearing
```

**OT 预条件器从快到稳定：**
| 预条件器 | 速度 | 鲁棒性 | 场景 |
|---------|------|--------|------|
| FULL_KINETIC | 最快 | 最低 | 常规绝缘体 MD |
| FULL_SINGLE_INVERSE | 中等 | 中等 | **默认选择**，兼容非整数占据 |
| FULL_ALL | 最慢 | 最高 | 困难体系，**需要 ENERGY_GAP 低估 HOMO-LUMO 带隙** |

**OT 不收敛时** → `MINIMIZER CG`（比 DIIS 更鲁棒）→ 更新预条件器 → `FULL_ALL + ENERGY_GAP 0.001`

**金属体系（强制对角化 + smearing）：**
```
&SCF
  EPS_SCF 1.0E-6
  MAX_SCF 200
  &MIXING
    METHOD BROYDEN_MIXING
    ALPHA 0.2       # 0.05（极难）→ 0.4（默认）
    NBUFFER 8
  &END MIXING
  &SMEAR ON
    METHOD FERMI_DIRAC
    ELECTRONIC_TEMPERATURE 300  # K
  &END SMEAR
&END SCF
```
- ALPHA 太大 → 振荡；太小 → 停滞
- NBUFFER 8-12（更多缓冲步 → 更稳定）
- 磁矩过渡金属：ALPHA 0.8-1.6 可能反而更好
- 含 H₂O 界面：ALPHA 低至 0.02

**CUTOFF/REL_CUTOFF 收敛测试协议**（来源：CP2K 官方 CUTOFF 教程）：
1. 固定 CUTOFF=400 Ry → 变化 REL_CUTOFF: 40, 50, 60, 70, 80 Ry
2. 选能量收敛达 ~1e-4 Ha 的 REL_CUTOFF（通常 60 Ry 足够）  
3. 再变化 CUTOFF 并固定选定的 REL_CUTOFF
4. 生产计算推荐：CUTOFF 400-600, REL_CUTOFF 60（TZVP）/ CUTOFF 600-800, REL_CUTOFF 60-80（TZV2P/QZVP）

**大基组线性相关 →** `ADDED_MOS 100-500` 增加空 KS 轨道

**电荷晃动/水溶液 →** `LEVEL_SHIFT 0.5-1.0 Ha` + 降低 ALPHA

**CP2K 自动化基础设施**（可直接调用）：
- `cp2k-output-tools`（官方 pip 包）：正则解析 SCF 步/能量/收敛状态
- `cp2k-input-tools`（官方 pip 包）：纯 Python 验证+编程修改输入参数

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

### Materials Studio (CASTEP / DMol3 / Forcite)

MS 是 BIOVIA 商业闭源软件，开源社区自动化工具极少。**没有 Custodian 或 AiiDA 级别的自动恢复框架。**
已有的 MS 解析器 `check_calc.py` (materials_studio parser) 覆盖基本输出解析。

**模块与运行方式**：

| 模块 | 输入文件 | 服务器启动命令 |
|------|---------|---------------|
| CASTEP | `*.cell` + `*.param` | `RunCASTEP.sh -np N inputname` |
| DMol3 | `*.car` + `*.input` | `RunDMol3.sh -np N inputname` |
| Forcite/Mesocite | `*.xsd` + Perl 脚本 | `RunMatScript.sh script.pl` |

**自动化方式**：GUI → "Copy Script" 生成 Perl 脚本 → 传脚本+结构到服务器 → `RunMatScript.sh` 执行。MS 2026 新增 Python 脚本支持。

**CASTEP SCF 不收敛 → 四级救援协议**（来源：MS 官方文档 + 计算化学公社 + 知乎）

```
Layer 1：基础参数（解决 90% 问题）
  取消 Fix Occupancy（金属体系头号杀手）
  Density Mixing → Charge 从 0.5 降至 0.1-0.2
  Max SCF cycles 100 → 200-500
  Smearing 0.1 → 0.2-0.5 eV
  Empty bands +20-30%

Layer 2：Density Mixing 深度调参
  mix_charge_amp 0.5 → 0.1（电荷密度混合振幅）
  mix_spin_amp 0.5 → 0.2（自旋密度混合，磁性体系关键）
  mix_energy_cutoff 增大到 Energy Cutoff ×3-4
  mix_history_length 增大到 10-20
  启用 Preconditioner

Layer 3：切换电子最小化方法
  Density Mixing → All Bands/EDFT
  收敛性大幅提升，但计算时间 ×3 以上
  适用于：孤立分子（超胞中的分子）、Density Mixing 反复失败

Layer 4：物理参数排查
  过渡金属/稀土 → 手动设置初始磁矩 + DFT+U
  亚铁磁体系（尖晶石等）→ 不同原子自旋方向（↑/↓）必须手动预设
  金属体系 → 增加 K 点密度
  截断能不足 → 增加 Energy Cutoff
```

**DMol3 SCF 不收敛 → 分层排查**：

```
Step A：验证物理设置
  自旋构型是否正确？（过渡金属 #1 失败原因：磁序设错）
  净电荷是否化学合理？
  初始几何是否合理？

Step B：数值质量
  提高 cutoff 和 k 点（降低精度反而加重不收敛）
  用 Medium 或 Fine，绝不使用 Coarse

Step C：算法调参
  Charge mixing 0.2 → 0.1 或 0.05（振荡时减小、停滞时增大）
  DIIS size 6 → 8-10
  Level Shift 0.1-0.3 Ha（等效于 Gaussian SCF=Shift）
  过渡金属 → 启用 Hexadecapole 多极展开
  小 smearing (0.005 Ha) → 收敛后撤掉

Smearing 铁律：0.005-0.01 Ha 可接受（熵贡献 ~1 meV/atom）
  >0.05 Ha → 结果物理上不可靠，电子结构可能畸变
```

**Forcite 几何优化不收敛 →**
```
- 减小 Max step size (0.5 → 0.2 Å)
- 力的收敛判据放宽：0.001 → 0.005 eV/Å
- 最大迭代步数 500 → 2000
- 检查力场原子类型分配是否正确
- 初始构型是否存在原子重叠或极度扭曲的键角
```

**CASTEP 自动重启**：MS 2026 声称 CASTEP & DMol3 支持自动重启收敛。旧版需手动：
```
检查 .castep 或 .dmol 输出 → grep "groundstate" 判断收敛
未收敛 → 保留 .check 文件（CASTEP）或 .dmol 最后构型 → 调整参数 → 重新提交
```

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

以上两步未解决时，读 `C:\Users\polestar\.claude\comp-chem-sop.md` 的 1→6 步排查流程。

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

## S6: Success Capture（成功经验捕获）

### 触发条件

某类计算错误连续 ≥3 次无法解决，Sunk-Cost Guardian 已触发，之后找到的方案**真正解决了根因**（不仅是巧合通过）。

### 排错场景中的"真成功"判别

| 场景 | 假成功 | 真成功 |
|------|--------|--------|
| VASP SCF 不收敛 | 把 ALGO 改成 All 后某次迭代巧合收敛 | ALGO=All + AMIX=0.2 + BMIX=1.0，后续所有体系（金属/绝缘体）均收敛 |
| CP2K OT 发散 | 重启后随机初始波函数某次收敛 | 切换 MINIMIZER 从 CG 到 DIIS + 调整 PRECONDITIONER，之后稳定收敛 |
| LAMMPS lost atoms | 减小 timestep 到 0.0001 勉强跑通 | 定位到初始构型原子重叠，修复后 0.001 timestep 正常 |
| Gaussian Link 9999 | 换了个初始构型凑巧过了 | 用 opt=calcfc 重新开始，之后所有类似体系都能收敛 |
| 远程 OOM | 换了大内存节点 | 定位到 NCORE 设置不当导致内存复制，调整后原节点也能跑 |

### 捕获工作流

```
错误复现 ≥3 次 → Sunk-Cost Guardian 停掉重试
  │
  ├─ 根因分析 → 输出诊断报告（JSON 格式，见 S4）
  │
  ├─ 方案验证
  │    ├─ 改参数 → pre-flight check 通过
  │    ├─ 提交 → hpc_job.py submit
  │    └─ 结果 → status=completed + check_calc.py 确认正常
  │
  ├─ 搜索归属
  │    在 diagnostics.md 中搜索：
  │    - 该代码段落（VASP/CP2K/LAMMPS/Gaussian/ORCA）有无相关条目
  │    - error_type 表中有无对应行可扩展
  │    - 是否有可合并的重复经验
  │
  ├─ 报告用户 → 等确认
  │
  └─ 写入到最精确的位置
```

### 写入位置决策树

```
问题只涉及一个代码的一个参数？
  → 追加到 diagnostics.md 该代码的对应错误类型段落下

问题涉及一个代码的多个参数/设置？
  → 追加到 diagnostics.md 该代码段落末尾，作为新的子段落

问题涉及跨代码通用机制（如 MPI、SCF 收敛理论）？
  → 追加到 diagnostics.md "第三步：通用排错" 段落

问题是全新领域（如新学了一个代码的排错套路）？
  → 新建 comp-chem/<code>_traps.md
  → 在 CLAUDE.md 域 2 触发词中加入该文件名

问题是 HPC/环境/服务器层面的？
  → 追加到 hpc.md 的对应策略段落
```

### 写入格式

```markdown
#### [错误类型]：[简短标题]

**识别特征**：[症状关键词，方便 grep 匹配]

**失败历史**：
| # | 尝试 | 结果 | 教训 |
|---|------|------|------|
| 1 | [具体改动] | [具体错误信息] | [为什么不行] |
| 2 | [具体改动] | [具体错误信息] | [为什么不行] |
| 3 | [具体改动] | [具体错误信息] | [为什么不行] |

**根因**：[一句话核心原因]

**成功方案**：`[具体参数/命令，可直接复制使用]`

**为什么有效**：[机制解释，1-3 句]

**适用条件**：[什么情况下用 / 什么情况下不适用]
```

### 与 Sunk-Cost Guardian 的联动

Sunk-Cost Guardian 是"止损"——≥3 次失败后不再盲目重试。
Success Capture 是"获利"——止损后找到的方案固化为永久资产。

两次 Sunk-Cost Guardian 触发之间，如果没有任何 Success Capture 写入，说明：
- 要么问题没解决（只是绕过了）
- 要么解决方案不可复现
→ **禁止对同一问题反复触发 Sunk-Cost Guardian 而不做 Success Capture**

## S7: Deep Retrospective（深度项目复盘）

> **通用复盘框架已独立为** `C:\Users\polestar\.claude\deep-retrospect.md`。
> 包含：CCRM 原则、SAMULE 三层分析、AgentErrorTaxonomy 失败分类、通用检查表（A-E）、报告模板、复盘后铁律。
> **首次触发 S7 时，先加载通用框架，再回来查看本节的领域特有补充。**

### 计算化学领域 — 补充检查项

**在完成通用检查表（deep-retrospect.md § 根本假设审查 A-E）的基础上，追加以下：**

**跨层诊断（AgentErrorTaxonomy × 计算化学）**：
- [ ] 所有失败是否集中在 Execution 层（OOM/超时/MPI）→ Planning 层可能有根本问题
- [ ] 是否试过"极端保守"参数（ENCUT=200, KPOINTS=1x1x1, 1 核）先确认基本能跑？
- [ ] 是否试过删除 WAVECAR/CHGCAR 从零开始（防止前次失败污染电荷密度）？
- [ ] 是否试过同一组输入在另一个代码中验证（VASP↔CP2K↔QE↔CASTEP）？

**计算化学专项假设审查**：
- [ ] 晶胞/超胞尺寸是否足够？Slab 层数是否合理？真空层是否真的需要当前大小？
- [ ] 表面终止面/吸附位点是否选择了最稳定的构型？
- [ ] 磁矩初始化是否与文献中的磁基态一致？是否试过非磁预收敛→磁矩重启？
- [ ] 泛函选择是否适合该体系（+U？范德华修正？杂化泛函？）
- [ ] 该体系是否有已知的计算难点（强关联、电荷转移、自旋交叉）需要特殊处理？
- [ ] POTCAR/赝势版本是否与泛函匹配？排序是否与 POSCAR 一致？

**联网搜索（计算化学专项，通用框架基础上追加）**：
```
python websearch.py "<材料名> <晶面> DFT calculation difficulties known issues"
python websearch.py "<材料名> computational parameters INCAR from literature"
```

**报告格式**：使用 `deep-retrospect.md` 的通用模板。计算化学特定发现填入"根本假设审查"段落。

---
# 收敛自动化工具与外部资源

本段列出已验证的生产级工具和研究，供构建自动收敛救援系统时参考。

## 生产级工具（可直接集成）

| 工具 | 覆盖代码 | 能力 | 许可 | 链接 |
|------|---------|------|------|------|
| **Custodian** | VASP, CP2K, NwChem, Q-Chem | 10+ 内置错误处理器，自动改 INCAR 并重启，>98% 成功率 | BSD | materialsproject.github.io/custodian |
| **ShakeNBreak** | VASP | 缺陷计算收敛监控+自动修复；切换 ALGO, ISPIN，跳过不可恢复体系 | — | github.com/SMTG-Bham/ShakeNBreak |
| **atomate2** | VASP, CP2K, Q-Chem | 预置工作流（能带/声子/弹性/介电）+ Custodian 集成 + FireWorks SLURM 调度 | BSD | materialsproject.github.io/atomate2 |
| **quacc** | VASP, QE, Q-Chem, MLPs | 高通量平台，多引擎分发（Parsl/Prefect/Covalent），Custodian 集成 | BSD-3 | github.com/Quantum-Accelerators/quacc |
| **AiiDA** | VASP, CP2K, QE, Gaussian, ORCA 等 | BaseRestartWorkChain：失败→改参→重启；完整溯源数据库 | MIT | aiida.net |
| **jobflow-remote** | 通用 | HPC 守护进程；双级错误分类（REMOTE_ERROR 自动重试+退避，FAILED 手动重试） | BSD | github.com/Matgenix/jobflow-remote |
| **cp2k-output-tools** | CP2K | 官方 pip 包，正则解析 SCF 步/能量/收敛状态 | — | github.com/cp2k/cp2k-output-tools |
| **cp2k-input-tools** | CP2K | 官方 pip 包，纯 Python 验证+编程修改输入参数 | — | github.com/cp2k/cp2k-input-tools |

## LLM Agent 系统（2025 年新兴）

| 系统 | 覆盖代码 | 方法 | 关键发现 |
|------|---------|------|---------|
| **VASPilot** | VASP | CrewAI 多 Agent（Manager+VASP+验证）+ MCP 工具 | 中科院出品；收敛测试+错误解析+参数调整+Web UI |
| **DREAMS** | VASP | 层级 LLM Agent + 共享画布 | 诊断 SCF 失败→建议 smearing/mixing_beta/mixing_mode/electron_maxstep |
| **El Agente Q** | ORCA, xTB | 22 Agent 层级 + 闭环恢复 | >87% 任务成功率；生成→验证→修复→重试 |
| **Masgent** | VASP, MLPs | `pip install masgent`；内置收敛测试模板 | MIT 许可 |
| **AutoDFT** | VASP | 7 Agent + History 存储+StepOutcomeSummary | 层级规划+每步监控裁决+自动恢复 |

## ML 辅助收敛

| 方法 | 机制 | 效果 | 来源 |
|------|------|------|------|
| 贝叶斯优化电荷混合 (Benaissa 2025) | BO 自动调 AMIX/BMIX | 比 VASP 默认参数更快收敛 | hal-04984658 |
| magman-llm | LLM 预测 SCF 收敛/发散 + 置信度 | 二进制输出，ROC-AUC 评估 | github.com/spdkit/magman-llm |
| 密度矩阵 ML 预测 (2024-2026) | 训练模型预测接近 SCF 解的初始密度矩阵 | SCF 步数减少 33-54% | 多篇 JCTC/JCP/arXiv |
| GAMMA 特征值自适应 | OUTCAR 特征值谱 → AMIX_optimal | 数学严格推导 | VASP wiki + MMSE 6905/8795 |

## 与本系统的集成路径

```
hpc_watcher.py 监控输出文件 mtime（已有）
  │
  ├─ 扩展：解析 OSZICAR/cp2k.out 的 SCF 收敛趋势
  │    ├─ dE 趋势分类：diverging / oscillating / stagnating / converging
  │    └─ 触发干预阈值 → 更新 .hpc_status.json 警告字段
  │
  ├─ 扩展：自动分级救援
  │    ├─ Level 1-3: 直接改 INCAR/input 参数（hpc_watcher 本地执行）
  │    ├─ Level 4-5: 需要 LLM 判断（下载输出→check_calc.py→Agent 分析→建议参数）
  │    └─ 参考 Custodian 的 handler 优先级经验
  │
  └─ 扩展：收敛经验归档 (S6)
       └─ 每次救援成功 → .hpc_status.json 记录 recovery_path → 归档进 diagnostics.md
```

## 参考来源

- VASP wiki Troubleshooting: https://www.vasp.at/wiki/index.php/Category:Electronic_Convergence
- VASP 讲座 Basics2 (Marsman): https://www.vasp.at/wiki/images/b/b6/VASP_lecture_Basics2.pdf
- CP2K OT 文档: https://manual.cp2k.org/trunk/CP2K_INPUT/FORCE_EVAL/DFT/SCF/OT.html
- CP2K CUTOFF 教程: https://manual.cp2k.org/trunk/methods/dft/cutoff.html
- SCF Convergence Guide (混合参数优化): surfchemsci.com / theochemsci.com
- Custodian 源码: https://github.com/materialsproject/custodian
- Woods et al. (2019): "Computing the SCF in KS-DFT" — J. Phys.: Condens. Matter
- Benaissa et al. (2025): "BO for DFT simulations" — Computational Condensed Matter
