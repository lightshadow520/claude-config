# Git Log — 项目改动记录

用户手动调用的 Git 存档技能。不自动触发，每次用户输入 `/git-log` 后执行。

---

## 两层记录机制

| 层级 | 调用方式 | 存在哪 | 例子 |
|------|---------|--------|------|
| **项目专属** | `/git-log <项目名>` | `55_玫瑰\<项目>\.git` | "ENCUT 400→350，OOM 解决" |
| **系统通用** | "总结到系统库" 或 `/git-log --system` | `C:\Users\polestar\.claude\knowledge-base\` | "VASP 6.4.3 OOM 排查 SOP" |

**Agent 判断逻辑**：
- 内容包含具体参数值、文件名、某次运行的细节 → 项目专属 → `/git-log <项目名>`
- 内容包含"以后遇到"、"所有项目"、"通用规则"、"SOP" → 系统通用 → `knowledge-base/`
- 拿不准 → 问用户

### 系统知识库结构

```
C:\Users\polestar\.claude\knowledge-base\
├── parameters/     ← 通用参数规则（如 "ENCUT ≥ 1.3×ENMAX"）
├── errors/         ← 排错 SOP（如 "Docker+OpenMPI X11 死锁"）
├── servers/        ← 服务器信息（如 "bjb1: MPICH, 32核, Docker"）
└── workflows/      ← 工作流经验（如 "提交前必做环境探测"）
```

### 系统库提交格式

Agent 自动判断内容分类，提交到对应子目录：

```bash
cd C:\Users\polestar\.claude\knowledge-base
git add <分类目录>/<文件名>.md
git commit -m "<分类>: <一句话总结>"
```

---

## 输入

用户提供项目文件夹名（如 "23"、"25-暖阳"、"Ni催化"），Agent 在 `E:\20250830_生物答疑\55_玫瑰\` 下模糊匹配完整文件夹名。

**用户不需要提供 commit message。** Agent 通过 `git diff` 或文件时间戳自动判断改动内容，生成 commit message。

---

## 执行步骤

### Step 1: 定位项目目录

```
Get-ChildItem "E:\20250830_生物答疑\55_玫瑰\<用户输入>*" -Directory
```

如果匹配到多个，列出让用户选。如果匹配到 0 个，报告并退出。

### Step 2: 检查 Git 仓库

```bash
cd "E:\20250830_生物答疑\55_玫瑰\<完整文件夹名>" && git rev-parse --git-dir 2>&1
```

- **有 .git** → 跳到 Step 4
- **没有 .git** → 执行 Step 3

### Step 3: 首次初始化（仅第一次）

```bash
PROJECT_DIR="E:\20250830_生物答疑\55_玫瑰\<完整文件夹名>"

# 创建 .gitignore
cat > "$PROJECT_DIR/.gitignore" << 'EOF'
OUTCAR
OSZICAR
WAVECAR
CHGCAR
CHG
DOSCAR
EIGENVAL
XDATCAR
LOCPOT
vasprun.xml
*.restart
*.wfn
*.cpt
*.tpr
*.edr
*.trr
*.xtc
*.gbw
*.check
*.mdcrd
*.nc
*.dcd
log.lammps
dump.*
*.castep
.hpc_status.json
__pycache__/
*.pyc
EOF

cd "$PROJECT_DIR" && git init
cd "$PROJECT_DIR" && git add .gitignore
cd "$PROJECT_DIR" && git commit -m "初始化项目 Git 记录"
cd "$PROJECT_DIR" && git add -A
cd "$PROJECT_DIR" && git commit -m "首次存档: 所有输入文件和脚本"
```

### Step 4: Agent 分析改动 + 提交

Agent 先检查改动内容，自动生成 commit message：

```bash
PROJECT_DIR="E:\20250830_生物答疑\55_玫瑰\<完整文件夹名>"

# 查看哪些文件变了
cd "$PROJECT_DIR" && git status --short
cd "$PROJECT_DIR" && git diff --stat

# 如果改动涉及参数修改，翻看具体 diff 生成描述
cd "$PROJECT_DIR" && git diff
```

Agent 根据 diff 内容自动生成 commit message，格式：`[改动类型]: [具体描述]`

- 参数修改 → `改参数: ENCUT 400→350, 原因: OOM`
- 输入文件更新 → `更新输入: POSCAR 替换为优化后构型`
- 脚本改动 → `脚本: plot_dos.py 加费米能级标注`
- 结果导出 → `结果: DOS 数据导出为 CSV`
- 一般存档 → `存档: 2026-06-10 提交前快照`

然后提交：

```bash
cd "$PROJECT_DIR" && git add -A
cd "$PROJECT_DIR" && git commit -m "<Agent 自动生成的 message>"
```

### Step 5: 展示结果

```bash
cd "$PROJECT_DIR" && git log --oneline -5
```

---

## .gitignore 规则

以下文件**不进 Git**（体积大 / 自动生成 / 敏感）：
- 计算输出：OUTCAR, OSZICAR, WAVECAR, CHGCAR, *.castep, *.log
- 检查点：*.restart, *.wfn, *.cpt, *.tpr
- 轨迹：*.trr, *.xtc, *.dcd, *.mdcrd, *.nc
- 临时文件：__pycache__, *.pyc, .hpc_status.json

以下文件**必须进 Git**：
- 输入：INCAR, POSCAR, KPOINTS, *.inp, *.gjf, *.com, *.cell, *.param, *.mdp
- 脚本：run_*.sh, *.py
- 文档：README.md, *.csv

---

## 输出

Agent 输出：
1. 项目目录完整路径
2. Git 仓库状态（新建 / 已有，当前分支，提交数）
3. 本次 commit 的 hash
4. 最近 5 条提交记录

---

## 示例

```
用户: /git-log 25-暖阳 降ENCUT到350解决了OOM

Agent:
  项目: E:\20250830_生物答疑\55_玫瑰\25-暖阳\
  Git: 已有仓库，3 次提交
  提交: a1b2c3d — 降ENCUT到350解决了OOM
  最近记录:
    a1b2c3d 降ENCUT到350解决了OOM
    e4f5g6h 首次存档
    i7j8k9l 初始化项目 Git 记录
```
