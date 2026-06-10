# VASP 计算经验心得

> 从 FeBiSe3+Pt 表面体系的惨痛调试中总结。每次新体系计算前建议快速扫一遍，避免重蹈覆辙。

---

## 一、环境就绪检查（跑前必做 3 项）

1. **确认赝势真伪**：`grep LEXCH POTCAR`，必须是目标泛函（PE=PBE, CA=LDA）。不要信目录名。
2. **确认环境变量**：`ulimit -s unlimited` + `export I_MPI_SHM_LMT=shm` + `export OMP_NUM_THREADS=1`
3. **确认物理核心数**：`lscpu | grep -E "Socket|Core|Thread"` → 物理核 = Socket × Core/Socket。MPI 进程 ≤ 物理核。

---

## 二、FEWALD 死锁（最常见卡死原因）

**症状**：OUTCAR 停在 FEWALD，进程占 CPU 但无进展，数小时不变。

**根因**：
- 长真空胞（>30A）导致 FFT 网格极度不平衡
- MPI 共享内存段残留（/dev/shm 未清理）
- HT 虚核过多导致 MPI 通信拥堵

**解决方案**（按优先级）：
1. `rm -rf /dev/shm/*` 然后重启
2. 换 `ALGO = All`（blocked Davidson 比 Normal 更容易过 FFT 初始化）
3. 减少 MPI 进程到物理核数
4. 缩小真空层（12A 通常够用，不要超过 20A）
5. 耐心等：某些体系 FEWALD 需要 1-3 小时自行通过

---

## 三、算法选择的优先顺序

```
首选: ALGO = All + NELMDL = -12 + AMIX = 0.2 + BMIX = 1.5
      ↓ 如果电荷剧烈振荡（dE > 500 eV）
备选: 在上方基础上 BMIX 降到 0.5，AMIN = 0.01
      ↓ 如果 FEWALD 阶段就死锁
尝试: ALGO = Normal（但可能更卡 FEWALD）
      ↓ 如果 3 组参数都失败
检查: 模型是否合理（原子重叠？真空过大？赝势正确？）
      或换 CP2K 试
```

**原则**：不要在 VASP INCAR 参数上调超过 3 轮。超了就检查模型，或换代码。

---

## 四、模型构建原则（追求"最小可行"）

| 参数 | 建议值 | 过度值（会慢/卡） |
|------|--------|-------------------|
| Slab 层数 | 2-3 层 | 4+ 层 |
| 超胞 | 1×1 或 2×1 | 2×2 以上 |
| 真空层 | 12-15 A | 20+ A（FFT 爆炸） |
| 总原子数 | <120 | 200+ |
| 固定底层 | 1 层原子 | 2+ 层 |

**Z 轴居中**：所有原子分数坐标 z 应在 0.15-0.85，不能贴边界（否则周期镜像干扰）。

---

## 五、计算提交前检查清单

```
☐ grep LEXCH POTCAR → 确认泛函类型
☐ ENCUT ≥ max(ENMAX) × 1.3
☐ POSCAR 元素顺序 = POTCAR cat 顺序
☐ 所有原子分数坐标 0 < xyz < 1
☐ Z 轴居中（表面模型 0.15-0.85）
☐ 环境变量：ulimit -s unlimited, I_MPI_SHM_LMT=shm, OMP_NUM_THREADS=1
☐ /dev/shm 已清理
☐ 先用小核数（4-8）试跑 5 分钟，确认能进 main loop
☐ 确认进 main loop 后再用目标核数正式提交
```

**最后一条最关键**——花 5 分钟验证能省几十小时。

---

## 六、表面/吸附体系的推荐 INCAR 模板

```
ENCUT   = 450            # 根据 POTCAR ENMAX 调整
EDIFF   = 1E-5
NELM    = 200
NELMDL  = -12            # 先做 12 步非自洽热身，防电荷振荡
IBRION  = 2
ISIF    = 2              # 弛豫离子，固定晶胞
NSW     = 150
EDIFFG  = -0.03
ISMEAR  = 0
SIGMA   = 0.05
ISPIN   = 2              # 含磁性过渡金属必开
IVDW    = 11             # DFT-D3，含表面吸附必开
ALGO    = All            # 过 FEWALD 最稳
AMIX    = 0.2
BMIX    = 1.5
AMIN    = 0.01
LDAU    = .TRUE.         # 含 Fe/Co/Ni 等过渡金属加 U
LDAUTYPE = 2
LDAUL    = -1  2  -1  -1
LDAUU    = 0.0  4.0  0.0  0.0
LREAL   = Auto
ISYM    = 0              # 表面模型关对称性
NCORE   = 4
LWAVE   = .TRUE.
LCHARG  = .TRUE.
```

---

## 七、POTCAR 管理

- 本地保留完整赝势库 tar.gz，每次部署从同一包解压
- **PBE 是表面/催化默认标准**，LDA 已基本淘汰
- LDA + IVDW=11 是物理错误组合（审稿人会拒）
- POTCAR 命名：标准版用裸名（Fe/），半芯态用 _pv/_sv（Fe_pv/），GW 用 _GW

---

## 八、常见错误的快速诊断

| 错误 | OUTCAR 关键词 | 根因 |
|------|--------------|------|
| XC 不兼容 | "Unsupported xc functional" | LDA 赝势 + IVDW，或 GGA 标签冲突 |
| 动能不足 | "kinetic energy error" | ENCUT < ENMAX |
| 原子太近 | "distance between some ions is very small" | Pt 团簇内 Pt-Pt ~2.77A 正常，超大警告才需处理 |
| FEWALD 死锁 | OUTCAR 停在 "FEWALD:" | 长真空 / 共享内存残留 / HT 超载 |
| 电荷振荡 | rms(c) 在 1-30 之间剧烈波动 | NELMDL 热身不够 / AMIX 太大 / BMIX 太小 |

---

## 九、能发文章的最终计算策略

1. **粗弛豫**（可以容错）：用 LDA 或 PBE + 宽松参数先把结构揉开，拿到 CONTCAR
2. **精弛豫**（必须正确）：用 PBE + IVDW=11 + 正确参数弛豫到力收敛
3. **静态计算**（出图用）：NSW=0 + 加密 K 点（3×3×1 或 5×5×1）+ LORBIT=11
4. **DOS 计算**：ICHARG=11 + 更密 K 点，不要用弛豫时的 Gamma-only

不要把前三步的参数混用——每步参数需求不同。

---

## 十、断点续跑（STOPCAR 安全重启）

> **核心原则**：永远不要 `kill` 正在跑的 VASP。用 STOPCAR 让它自己停下来并保存进度。
> 进度存在 WAVECAR+CHGCAR 里，重启后从断点继续，一步都不浪费。

### 场景 A：NSW=0 静态计算 — 用 LABORT 中止 SCF

当静态计算 SCF 收敛太慢、想中途放宽 EDIFF 时，**不能直接 kill**（WAVECAR=0，进度全丢）：

1. 在计算目录创建 `STOPCAR`，写入：
   ```
   LABORT = .TRUE.
   ```
   （`LABORT` 专门中止 SCF 电子迭代。VASP 跑完当前步后读到它，自动写 WAVECAR+CHGCAR 然后安全退出。）

2. 等 VASP 自动退出（轮询 `ps aux | grep vasp_std | grep -v grep | wc -l` 直到 0，最长等 15 分钟）。

3. 验证遗产：`ls -lh WAVECAR CHGCAR`，确认文件 >0 且修改时间是刚停的时间。

4. 备份：`cp -r run_dir/ run_dir_backup_$(date +%Y%m%d_%H%M%S)/`

5. 修改 INCAR：
   ```
   EDIFF = 1E-4    # 放宽收敛标准
   ISTART = 1       # 读 WAVECAR
   ICHARG = 1       # 读 CHGCAR
   ```
   **只改这三行，其它参数一个不动。**

6. 删掉 STOPCAR，重新提交。重启后 OSZICAR 第一步能量应紧接中断前，10 步内收敛。

### 场景 B：NSW>0 几何优化 — 用标准 STOPCAR

弛豫中途想暂停/改参数：

1. 在计算目录创建 `STOPCAR`（空文件即可，或写 `STOP`），VASP 在当前离子步完成后自动退出。**WAVECAR 正常写，CONTCAR 保留最后结构。**

2. 后续步骤同上 3-6。

### 场景 C：OOM 被系统杀掉后的续跑

如果 VASP 被 OOM Killer 或意外断电杀掉：只要运行中有正常写出的 WAVECAR（NSW>0 每个离子步结束 / NSW=0 收敛后），就可以用 ISTART=1 + ICHARG=1 续跑。**但 NSW=0 中途被 kill 掉的 WAVECAR=0，无法续跑，只能用 STOPCAR 方法。**

### 重启 INCAR 三件套（缺一不可）

```
ISTART = 1    # 0=从头, 1=读 WAVECAR
ICHARG = 1    # 0=从 WAVECAR 算电荷, 1=直接读 CHGCAR, 11=非自洽
EDIFF = 1E-4  # 放宽后的收敛标准
```

### 常见踩坑

| 坑 | 现象 | 预防 |
|----|------|------|
| 用 kill -9 | WAVECAR=0，进度灰飞烟灭 | 只用 SIGTERM（见下方） |
| 忘删 STOPCAR | 重启后立马又停 | `rm STOPCAR` 后再提交 |
| 忘加 ISTART=1 | 从头算，白费之前的收敛 | INCAR 里确认三件套 |
| ICHARG=11 用于自洽 | 不迭代电荷密度，结果不靠谱 | 自洽续跑用 ICHARG=1 |
| 备份在同一个盘 | 盘满了覆盖原始文件 | 验证备份路径有足够空间 |
| NSW=0 用 LABORT | MPI_Abort 死锁，WAVECAR=0 | 见下方"如何安全中断" |

---

## 十一、中断与续跑的正确方法（血泪教训）

### 如何安全中断正在运行的计算

**NSW=0 静态计算 — 用 SIGTERM（不是 STOPCAR！）**：

STOPCAR + `LABORT=.TRUE.` 调用的是 `MPI_Abort`，跳过所有正常 I/O 清理。实测 116 原子体系（VASP 6.4.3）LABORT 触发死锁，WAVECAR 从头到尾 0 字节。

正确做法：
```bash
# 1. 先备份（安全兜底）
cp -r run_dir/ run_dir_backup_$(date +%Y%m%d_%H%M%S)/

# 2. 找到 mpirun PID
ps aux | grep mpirun

# 3. 发 SIGTERM（不是 -9！）
kill <mpirun的PID>

# 4. 等 VASP 正常退出，确认 WAVECAR 非零
ls -lh WAVECAR CHGCAR
```

`kill`（不带 `-9`）走的是 MPI_Finalize 流程——VASP 会把 WAVECAR 和 CHGCAR 完整写盘后正常退出。这是我们这次 OOM 死锁后唯一救回数据的方式。

**NSW>0 弛豫计算 — 用 STOPCAR（空文件）**：

```bash
touch STOPCAR     # VASP 跑完当前离子步自动停，CONTCAR 早已写盘
```

弛豫每个离子步结束时 VASP 会检查 STOPCAR，发现即停。WAVECAR 和 CONTCAR 完整。

### 续跑的 INCAR 三件套

```
ISTART = 1    # 读 WAVECAR
ICHARG = 1    # 读 CHGCAR
EDIFF = xxx   # 可以保持不变或放宽
```

### WAVECAR 能不能丢

**NSW=0**：WAVECAR 只在退出时写盘。中途 kill -9、LABORT 死锁、OOM 被系统杀 → WAVECAR=0 → **所有电子迭代进度全丢**。

**NSW>0**：每个离子步结束写 WAVECAR。即使被 OOM 杀了，上一个离子步的 WAVECAR 还在。

**教训**：NSW=0 长时间算静态，每几小时手动 `cp -r` 备份一次目录。WAVECAR 只有退了才有，跑了 300 步还没退 = WAVECAR 仍是 0。

### 续跑验证清单

从 VASP 重启日志确认三行：
```
found WAVECAR, reading the header          # → 波函数继承成功
charge-density read from file: <SYSTEM>    # → 电荷密度继承成功
entering main loop                         # → 首步能量紧接中断前
```

如果看到 `WAVECAR not read` → ISTART 没设或 WAVECAR 损坏。如果 `charge-density` 没出现 → ICHARG 没设或 CHGCAR 损坏。

---

## 十二、杀进程铁律（Agent 必读）

**严禁 `pkill`、`killall`、`pkill -9` 等广播式杀进程命令。** 原因：无差别杀死所有同名进程，一条命令毁掉所有正在跑的计算。

### 强制流程

**第一步：列出所有进程及其用途**

```bash
# 列出每个 mpirun 及其子进程的工作目录
for pid in $(pgrep mpirun 2>/dev/null || ps aux | grep mpirun | grep -v grep | awk '{print $2}'); do
    children=$(ps --ppid $pid -o pid= 2>/dev/null | head -1)
    cwd=$(readlink /proc/$children/cwd 2>/dev/null || echo "unknown")
    cpu=$(ps -o time= -p $pid | tr -d ' ')
    echo "mpirun PID=$pid CWD=$cwd CPU=$cpu"
done
```

**第二步：输出表格让用户确认**

```
发现以下 VASP 进程：
  mpirun PID=77588 CWD=/root/Pt4_cluster CPU=00:15:32 → Pt4 团簇计算
  mpirun PID=65559 CWD=/root/FeBiSe3_slab CPU=1052:56 → FeBiSe3 slab 计算

将要杀掉: PID=77588 (Pt4 团簇)
保留:     PID=65559 (FeBiSe3 slab)
确认? [y/n]
```

**第三步：精准杀，逐个核验**

```bash
kill <PID>           # 只杀这一个，SIGTERM
# 确认已退出: ps -p <PID> 返回空
```

### 铁律

| 禁止 | 原因 | 正确做法 |
|------|------|---------|
| `pkill vasp_std` | 杀掉所有目录的所有计算 | `kill <具体PID>` |
| `killall mpirun` | 同上 | `kill <具体PID>` |
| `pkill -9` | 跳过 MPI_Finalize，CHGCAR=0 | 永不用 -9 |
| 不查 CWD 就杀 | 可能杀掉正在跑的重要计算 | 先 `readlink /proc/$PID/cwd` |
| 看名字就杀 | 不同目录的同名进程互不相干 | 先列全表，确认后再动手 |

此规则适用于所有 Agent、所有脚本、所有操作人员。违反一次即可能造成数天计算进度的损失。
