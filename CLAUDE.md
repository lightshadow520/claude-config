# 识图能力

你的底层模型不具备原生识图能力。遇到图片时，**不要用 Read 工具看图片**，改用 vision.js：

```
node <scripts_dir>/vision.js "<图片路径>" "用中文描述这张图片"
```

## 触发场景

- 用户分享图片路径（本地或网络 URL）
- 消息中出现 "Saved attachments:" 并列出图片
- 用户要求分析、描述、识别图片内容
- **重要**：对于网络图片 URL，使用 `--url` 参数：
  ```
  node <scripts_dir>/vision.js --url "<图片URL>" "用中文描述这张图片"
  ```

## 注意事项

- 如果用户一次发多张图片，对每张图片依次执行 vision.js
- 拿到所有图片的文字描述后再统一回复
- 不要跳过识图步骤，也**不要用 Read 工具直接读取图片**

# 联网搜索

你的底层模型不具备原生联网能力。需要联网搜索时，使用 websearch.py：

```
python <scripts_dir>/websearch.py "<搜索关键词>" --count N
```

- `--count N` 控制返回结果数，默认 10
- `--json` 输出 JSON 格式

## 触发场景

- 用户问当前事件、最新资讯、新闻
- 用户说"搜索""联网""查一下""搜一下"
- 用户要求的信息超出你的知识截止日期
- 你需要确认某个信息是否仍然准确
- 用户问最新版本的库/工具文档

## 注意事项

- 优先用用户提问的语言搜索；技术问题可中英文各搜一次
- 多个独立子问题时并行搜索
- 回复时引用来源 URL
- 结果质量差时换个说法重新搜索

## WebFetch 被拒时的降级方案

**WebFetch 从 Anthropic 服务器发起，学术域名（.ac.uk, .edu）、GitHub Pages（github.io）经常因不在安全白名单而被拒。** 这不是你的网络问题。

遇到 `Error: Unable to verify if domain X is safe to fetch` 时，立即降级为本地抓取：

```
python <scripts_dir>/websearch.py --fetch "<URL>" --strip
```

- `--strip` 去除 HTML 标签输出纯文本（推荐，token 友好）
- 不加 `--strip` 输出原始 HTML（需要完整页面源码时用）
- 本地 `urllib.request` 不受 Anthropic 安全过滤器限制
- 默认截取前 8000 字符，超长页面自动截断

**禁止** 在 WebFetch 被拒后直接放弃或反复重试——直接走本地抓取。

# Word 文档阅读

你的底层模型不具备原生阅读 Word 文档的能力。遇到 `.docx` 文件时，**不要用 Read 工具直接读取**，改用 read_docx.py：

```
python <scripts_dir>/read_docx.py "<文件路径>"
```

## 触发场景

- 用户分享 .docx 文件路径
- 用户要求读取、分析、总结 Word 文档内容
- 消息中出现 "Saved attachments:" 并列出 .docx 文件

## 注意事项

- 脚本提取所有段落和表格文本（保留标题层级）
- 不支持旧版 `.doc` 格式；如遇 .doc 文件，提示用户先用 LibreOffice 转为 .docx
- 提取到的文本较长时，先理解全文再回应用户

# Origin OPJU 数据提取

你的底层模型不具备原生读取 Origin `.opju` 文件的能力。遇到 `.opju` 文件时，**不要用 Read 工具直接读取**，改用 opju_extract.py：

```
python <scripts_dir>/opju_extract.py "<文件路径>"          # 查看内容
python <scripts_dir>/opju_extract.py "<文件路径>" --csv    # 导出 CSV
```

也可以直接用 `originpro` 库在 Python 代码中提取（详见 opju-extract skill）。

## 触发场景

- 用户分享 .opju 文件路径
- 用户要求提取、读取 Origin 项目数据
- 用户提到 "opju"、"Origin 数据提取"、"Origin 工作表导出"

## 注意事项

- 需要电脑上安装了 Origin/OriginPro 软件
- 需要 `pip install originpro pandas`（originpro 通过 COM 接口与 Origin 通信）
- 提取的 CSV 使用 UTF-8 BOM 编码，Excel 可直接打开
- 图表 (GPage) 不包含表格数据，只导出 Workbook 中的 Worksheet

# GitHub 配置同步

将用户级 Claude Code 配置上传/同步到 GitHub 仓库。详见 sync-to-github skill。

**仓库**: `lightshadow520/claude-config` (https://github.com/lightshadow520/claude-config)

## 触发场景

- 用户说"上传配置到 GitHub"、"同步到 GitHub"、"备份 Claude 配置"
- 用户要求更新/发布新版本的配置仓库
- 用户要求分享用户级能力给其他人

## 隐私保护（强制）

上传前**必须**检查并处理：

1. **API Key**：扫描所有文件的 `sk-` 模式，`settings.json` 中的 token 替换为占位符
2. **绝对路径**：仓库 CLAUDE.md 用 `<scripts_dir>` 占位，本地 CLAUDE.md 保留真实路径
3. **个人邮箱/用户名**：README 中的 Git 配置信息脱敏

## 版本管理

- 每次更新后打 tag：`v1.0.0` → `v1.0.1` → ...
- Commit message 说明改动内容
- 本地 `~/.claude/` 是权威源，修改从本地同步到仓库

# SCI Color Palettes

For scientific color schemes, use sci_colors.py — pure terminal ANSI, no PNG needed:

```
python <scripts_dir>/sci_colors.py                              # overview (55 palettes, grouped)
python <scripts_dir>/sci_colors.py --show "<name>"              # detail: large blocks + hex
python <scripts_dir>/sci_colors.py --search "<keyword>"         # search by keyword
python <scripts_dir>/sci_colors.py --code "<name>"              # copy-paste Python snippet
python <scripts_dir>/sci_colors.py --tag "<tag>"                # filter by tag
```

See sci-color skill for detailed guidance. Show terminal output directly — never generate PNG files for color preview.

## Trigger

- User asks about colors, palettes, color schemes, chart aesthetics
- User says "配色", "颜色", "sci颜色", "好看的配色"
- User needs colorblind-safe / print-friendly / journal-grade colors

## Quick Ref

| Scenario | Palette |
|----------|---------|
| 3-5 categories | Nature Classic 5 / Science Colorblind 6 |
| Heatmap / sequential | Viridis 5 / Cool-Warm 5 |
| Colorblind-safe (gold std) | Okabe-Ito 7 / Tol Muted 9 |
| Single-cell / multi-omics | Nature 2020 COVID 12 / Cell 2019 scRNA 8 |
| Soft / elegant / artsy | Morandi 6 / French Gray 6 |
| Dark bg (PPT/poster) | Neon DarkBg 5 |
| Semantic (good/warn/bad) | Traffic Light 3 |

# /workflow 多代理工作流

`CLAUDE_CODE_WORKFLOWS=1` 已启用。Workflow 是 JS 脚本驱动的确定性多代理编排工具。

## 主动建议（Proactive Suggestion）

遇到以下场景时，**主动提醒用户**可以考虑使用 /workflow，并**自行帮用户编写 .js 工作流脚本**（用户不会写也不应需要写）：

### 触发场景

- **批量处理**：多个文件/数据集需要相同操作（如批量提取 opju、批量画图）
- **多步骤流水线**：提取→分析→画图→出报告，步骤之间有明确依赖
- **并行独立任务**：同时 review 多个文件、同时分析多个系统
- **重复性工作**：用户以前做过的类似任务再次出现
- **需要确定性**：用户说"每次结果都不太一样"时

### 提醒方式

在判断可以用 workflow 加速时，简洁地提一句：

> "这个任务可以并行跑，要不我写个 workflow .js 脚本？8 个文件 30 秒就处理完了。"

提供两个选项：
1. **自动写脚本**：Claude 直接写好 .js，用户只需确认后运行 `/workflow xxx.js`
2. **传统方式**：继续在主会话里顺序执行

### 脚本编写规则

- 用户不会创建 .js 文件，Claude 负责写完整脚本
- 脚本放项目根目录或 `.claude/workflows/` 下
- 每个 `agent()` 任务描述要具体（指定工具、文件路径、预期输出）
- 加上验证步骤（agent 跑完检查结果完整性）

# 计算化学与 HPC（条件加载）

下面两个领域文件按需加载，避免每次对话都占 token。
**触发规则：对话命中相应关键词后，必须先用 Read 工具加载对应文件，再执行任何操作。**

## 域 1：服务器 & HPC 操作

**触发词**（命中任一即加载）：
SSH、远程服务器、host、mpirun、vasp_std、cp2k、lammps、gaussian、orca、
nohup、提交计算、查看进程、kill 进程、服务器进程、hpc_job、hpc_watcher、
remote_ps、连接超时、服务器负载、queue、作业调度、autodl、AutoDL、
docker、Docker、容器、GPUshare、多线程加速、MPICH、OpenMPI

→ **加载** `<config_dir>/comp-chem/hpc.md`

## 域 2：计算报错 & 诊断

**触发词**（命中任一即加载）：
报错、失败、不收敛、收敛了吗、OOM、内存不足、死锁、deadlock、segfault、
FEWALD、SCF、几何优化、还要多久、什么时候跑完、预估时间、进度如何、
log、OUTCAR、OSZICAR、输出文件、check_calc、error_type、排错、诊断、诊断

→ **加载** `<config_dir>/comp-chem/diagnostics.md`

### 结构化错误查询（域 2 子工具）

命中域 2 触发词后，优先用结构化错误库检索，比全文 grep 更精确：

```
python <scripts_dir>/query_errors.py --type <error_type> --suggest
python <scripts_dir>/query_errors.py --search "<关键词>"
python <scripts_dir>/query_errors.py --type <error_type> --json  # Agent 消费
```

错误库位置：`<config_dir>/comp-chem/error_db.json`（11 种 error_type，65+ 修复方案）

### 工具注册表

所有脚本的标准接口定义在 `<config_dir>/comp-chem/tool_registry.json`，Agent 可用 `grep "name"` 发现工具、用 `input_schema` 了解参数契约。
组合模式（`composition_patterns`）定义了多工具编排流程（诊断/提交/监控）。

## 域 3：深层排查（在域 2 不够用时）

→ **加载** `<config_dir>/comp-chem-sop.md`

## 不触发加载的话题

以下话题不需要加载上述文件，正常回答即可：
- 理论方法选择建议（用什么泛函、基组）
- 计算化学行业讨论
- 代算业务相关
- 数据存储、SOP 管理

# 深度项目复盘（条件加载）

**适用范围：所有类型的项目**——软件开发、科学计算、数据处理、ML 训练、系统运维等。

**触发词**（命中任一即加载）：
复盘、深度分析、来龙去脉、为什么总是失败、根本上有没有问题、
反思一下、梳理一下、问题出在哪、连败、反复失败、同一个坑

→ **加载** `<config_dir>/deep-retrospect.md`

该文件包含通用复盘框架（CCRM、SAMULE 三层分析、AgentErrorTaxonomy、前提假设审查检查表、通用复盘报告模板）。
各领域文件（comp-chem/hpc.md、comp-chem/diagnostics.md）包含该领域特有的补充检查项。

加载流程：
1. 先加载 `deep-retrospect.md`（通用框架）
2. 再根据项目领域加载对应的领域文件中的 S7 补充检查项

# Agent 可靠性五大策略（全局默认生效）

以下策略源自 2025-2026 年前沿 Agent 工程研究，所有任务默认执行。详细实施规则见各领域文件。

## 1. Schema-Gated Execution（模式门控）

**生成自由，执行严格。** 任何改变系统状态的操作，必须先通过校验门：
- 提交远程计算 → 必须走 `hpc_job.py`（禁止裸 `mpirun`/`nohup`）
- 修改输入文件 → 先 diff，展示变更内容，等用户确认
- 杀进程/重启/删文件 → 必须走审批流程（见"高危操作审批"）
- 修改代码/配置 → 先在临时副本测试，通过后再应用

## 2. Generator ≠ Reviewer（生成与审查分离）

**禁止同一个上下文既写又审。** 产出物必须经独立视角审查：
- 生成代码/INCAR/脚本后，检查逻辑一致性（至少用不同推理路径复核一遍）
- 重大修改时，列出变更清单 + 每项变更的理由
- 输出关键判断时，标注置信度：`[确信]` `[大概率]` `[待验证]`

## 3. Context Engineering（上下文工程）

**上下文是稀缺资源，每行都必须有存在理由：**
- CLAUDE.md 分层触发（通用 → 领域文件关键词触发 → 子领域按需加载）
- 状态信息写入结构化文件（`.hpc_status.json`），不依赖对话记忆
- 避免在对话中重复大段日志/输出——用文件路径引用
- 长任务用子代理隔离，主代理保持编排视角

## 4. CodeAgents（结构化通信）

**Agent 间通信和状态传递用结构化格式，降低歧义和 token 消耗：**
- 任务参数用 JSON/YAML key=value，不用自然语言段落
- 错误报告用 `{error_type, suggestion, evidence}` 三元组
- 进度报告用 `{status, elapsed, eta, last_activity}` 五元组
- 参数修改用 `{param, old_value, new_value, reason}` 四元组

**结构化基础设施**（大厂工程化标准）：
- **错误知识库**：`comp-chem/error_db.json` — 11 种 error_type 的结构化诊断与修复方案
- **工具注册表**：`comp-chem/tool_registry.json` — 10 个脚本的标准化接口定义（input_schema/output/triggers）
- **任务数据库**：`comp-chem/job_schema.sql` — SQLite schema，支持历史查询/收敛预估/错误模式挖掘
- **查询工具**：`scripts/query_errors.py` — 精确检索错误库，替代 grep 全文搜索

## 5. Cognitive Firewalls（认知防火墙）

**关键操作前自动触发验证，不通过不执行。** 违反以下任一即视为错误：

| 防火墙 | 触发条件 | 动作 |
|--------|---------|------|
| Hallucination Guard | 引用未见过的文件/路径/API/INCAR 标签 | 先用 grep/Read 验证其存在 |
| Devil's Advocate | 用户问"X 是对的吧？" | 先生成最强反方论证，再回答 |
| Sunk-Cost Guardian | 同一方案连续失败 ≥3 次 | 停止重试，列出替代方案，询问用户 |
| Premature Closure | 声称"完成了"、"修好了"、"跑通了" | 抽查边界条件是否真正通过 |
| Authority Deference | 声称"文档说 X"、"论文建议 Y" | 验证该特性/版本是否在当前代码/输入中可用 |

## 6. Success Capture（成功经验捕获）

**同一个坑踩 ≥3 次后终于绕开 → 必须主动询问是否固化为规则：**

触发条件：
- 同一问题/同类错误连续失败 ≥3 次
- 某个方案**真正成功**（后续操作完全绕开了这个坑，不是巧合通过）
- → 主动问用户："这个坑踩了 N 次才解决，要不要写入规则避免以后再踩？"

捕获流程：
1. **搜索现有文件**：在 `comp-chem/` 和 `memory/` 下搜索与该问题相关的已有 md
2. **有相关文件** → 报告找到了哪个文件 + 相关段落 → 问是否追加到该文件
3. **无相关文件** → 问是否新建细分 md，放在合适的层级（comp-chem/ 下或更深的子目录）
4. **写入格式**：`问题描述 → 失败历史（每次试了什么为什么不行）→ 成功方案（为什么这次能绕开）→ 识别特征（以后遇到什么症状就想到这个规则）`
5. **根级只放触发规则**，具体经验下沉到最相关的细分文件

## 7. Deep Retrospective（深度项目复盘）

**同一项目/任务跨多轮对话连续失败，且 Sunk-Cost Guardian 或 Success Capture 已触发 → 执行系统性深度复盘。**

触发条件（任一）：
- 同一方向/项目的不同尝试累计失败 ≥3 次
- 用户说"深度分析""复盘""来龙去脉""为什么总是失败""根本上有没有问题""反思一下"
- Sunk-Cost Guardian 已触发但 Success Capture 未找到真成功方案
- 同一坑反复出现跨不同代码/服务器/参数组合

复盘流程：
1. **收集全部失败记录**：列出每次的 error_type、尝试方案、失败表现
2. **分类失败模式**：按 AgentErrorTaxonomy — Planning失败/执行失败/参数错误/环境问题/根本假设错误
3. **检查根本假设**：建模假设（晶胞大小、slab层数、真空层）是否正确？计算方法选择（泛函、基组、赝势）是否适合该体系？
4. **联网搜索替代方案**：用 websearch.py 搜索该体系的最新文献/已知问题/社区讨论
5. **输出复盘报告**：失败模式分类 → 根因判断 → 假设验证结果 → 替代路径建议 → 置信度标注
6. **等用户确认后再执行任何新方案**（严禁复盘后直接动手）

根级只放触发规则，具体分析框架和检查表见领域文件。

**注意**：这些策略增加 ~20% token 开销，换取确定性大幅提升。对于科学计算（一次跑几天甚至几周），可靠性 > 速度。

# 高危操作审批

以下操作**必须先暂停并询问用户意见**，得到明确同意后才能执行。**违反即视为严重错误**：

1. **终止进程/任务**：杀死任何正在运行的程序、服务、或后台任务。包括但不限于：
   - Shell 命令：`pkill`、`kill`、`killall`、`taskkill`、`Stop-Process`
   - **Claude Code 工具：`TaskStop`（停止后台任务）**
   - 关闭/退出任何应用程序

   **审批前必须列出进程清单**：在询问用户是否终止进程时，必须先运行进程查看命令（如 `tasklist /v` 或 `ps aux` 或 `Get-Process`），完整列出所有运行的进程/僵尸进程，标注哪些占用了高 CPU/内存，让用户清楚看到当前系统负载状况再决定。进程太多容易卡死，用户需要全局视角来判断。
2. **大规模重跑**：删除已有运行结果并从头重跑计算任务（包括 `rm -rf` 运行目录后重启）
3. **删除文件**：`rm -rf` 任何可能包含用户数据的目录或文件
4. **修改系统配置**：更改系统级配置文件、环境变量、权限设置

在询问用户时，必须：
- 先列出进程清单/数据状态（先让用户看清全貌）
- 说明你提议的操作及其后果（会丢失什么）
- 给出保留现有数据的替代方案

# 计算任务监看规则（严禁擅自修改）

**正在运行的远程计算任务，严禁在未经用户明确指令的情况下做任何修改操作**，包括但不限于：

- **严禁** 自行杀掉计算进程（kill/pkill/killall）
- **严禁** 自行修改 INCAR、POSCAR、KPOINTS、POTCAR、run_vasp.sh 等输入文件
- **严禁** 自行切换 ALGO、ENCUT、EDIFF 等算法参数
- **严禁** 自行重启计算或清理工作目录
- **严禁** 自行修改核心数（-np）、OpenMP 线程数等运行参数
- **严禁** 以"这个参数更好""之前跑通过"等理由自行决策修改

**正确做法**：发现问题时，汇报当前状态 + 分析原因 + 提出建议方案，**等用户明确说"改"之后才能动手**。
