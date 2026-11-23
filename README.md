# PdfRenamer — 本地 PDF 信息提取与批量更名工具

一款**纯本地、零 AI、零联网**的 Windows 桌面软件：选一个文件夹，按「论文 / 合同」两种模式提取 PDF 里的关键信息，按可编辑模板批量重命名，并在**所选目录**自动生成 `信息汇总.xlsx`。

> 「利用 AI 编程」指开发方式；**软件内部不嵌任何大模型 / 云端 API / 推理库，零联网**。信息提取依靠 PDF 既有文本层、PDF 元数据 + 首页版式的确定性解析、关键词与正则表达式。对**无文本层的扫描件**，仅调用 **Windows 10/11 操作系统内置的离线 OCR**（`Windows.Media.Ocr`）把图片文字转成本地文本，再交给同一套规则处理——不是大模型、不联网、不新增 Python 依赖。目标机缺中文 OCR 语言包时优雅降级为「保持原名 + Excel 标记需人工处理」。

> **V1.1.2 更新**：真实合同扫描件可自动识别（系统内置离线 OCR）、预览表**双击行可人工补录字段**、UI 排版精简不冗余、配置升级到 v5（用户自定义字段/正则/模板不丢）、扫描件正向校准 4/4 判为合同。更多历史更新见下方「版本记录」。

> **V1.1.1 更新**：合同模式新增文档类型闸门（拦截绩效评价报告等非合同公文）、界面可**单独选择一个或多个 PDF 文件**（须同一目录）、现代浅色主题与底部状态栏、Excel 追加「PDF 类型」标签列（旧表无损升列）、中文合同规则通用性增强、配置自动升级到 v4。

---

## 1. 直接使用（无需 Python）

| 文件 | 说明 |
|---|---|
| `dist/PdfRenamer.exe` | 绿色单文件，双击即用，不写注册表 |
| `dist/PdfRenamer_setup.exe` | 带安装向导的安装包，可创建桌面快捷方式、可从「添加/删除程序」卸载 |

首次启动会让你选择 **论文** 或 **合同** 模式；勾选「记住本次选择」后下次直接进入，也可随时从「模式」菜单切换。

### 操作四步

1. **选择要处理的 PDF**：默认「整个文件夹」，点「浏览…」会显示直属 PDF 数量（不递归子目录）；也可切到「单独选择 PDF 文件…」一次勾选多个文件（**须位于同一目录**，跨目录会提示按目录分批处理）。两种方式的 `信息汇总.xlsx` 都固定生成在这些文件所在目录。
2. **配置字段与模板**（可选）：左侧可新增/删除/排序字段，每个字段可填「标签关键词」、可选的「正则表达式」和「结构化来源」下拉；右侧编辑命名模板，如 `{合同名称}_{甲方}_{供方}_{时间}`。论文模式默认启用结构化来源，用于解析没有「Title: xxx」标签的英文期刊/会议论文首页。
3. **① 扫描并预览**：后台逐份提取，只生成改名计划，**不改动任何文件**。核对预览表（原文件名 / 新文件名 / 状态 / 缺失字段 / 备注）。
4. **② 确认执行**：二次确认后原地改名并写出 `信息汇总.xlsx`。若结果不满意，点「撤销上次重命名」即可完整还原。

- 「恢复上次结果」：Excel 正被打开导致写入失败时，关闭 Excel 后点它即可从增量日志补写。
- 扫描件、加密件、乱码件**不会改名**，会在 Excel 标红「需人工处理」。

---

## 2. 目录结构

```
PdfRenamer/（项目根目录，可克隆到任意路径）
├─ dist/PdfRenamer.exe              绿色单文件
├─ dist/PdfRenamer_setup.exe        安装向导
├─ docs/需求分析说明书.docx         需求分析
├─ docs/PRD产品需求文档.docx        PRD 拆解
├─ src/pdfrenamer/                 全部源码
│  ├─ app.py / __main__.py         入口（含 --selftest）
│  ├─ models.py / presets.py       数据模型、两套模式出厂预设
│  ├─ rules.py / config.py         清洗归一化、配置持久化（v5 链式迁移）
│  ├─ structured.py                ★论文 PDF 元数据 + 首页版式解析（纯规则）
│  ├─ contract_gate.py             ★V1.1.1 合同文档类型闸门（纯规则）
│  ├─ extractor/ocr_winrt.py       ★V1.1.2 Windows 系统内置离线 OCR 补文（零新增依赖）
│  ├─ extractor/                   PDF 后端（pymupdf / pypdf / pdfplumber）
│  ├─ engine.py / renamer.py       提取引擎、重命名引擎
│  ├─ undo.py / excel.py           还原日志、Excel 汇总
│  └─ ui/                          tkinter 界面（模式选择 / 主窗口 / 字段编辑器 / theme 现代浅色主题）
├─ src/launcher.py                 PyInstaller 入口（绝对导入）
├─ config/default_config.json      出厂预设（打包进 exe）
├─ assets/app.ico                  图标
├─ build/                          spec、bat、Inno Setup .iss、图标/文档生成脚本
├─ tests/                          单元测试、UI 冒烟、合规扫描、校准脚本
│  └─ samples/                     合同/论文样本 PDF **不入库**，需运行 tests/make_samples.py 本地生成
├─ samples/user/                   真实样本（仅本机，已在 .gitignore 中排除）
├─ output/html/                    两份 Word 的排版 HTML 中间产物
├─ wheels/                         离线 wheel 兜底
└─ requirements.txt / README.md
```

配置与日志写在 `%APPDATA%/PdfRenamer/`（`config.json`、`plans/`、`rows/`）。
**唯一写进用户所选目录的文件是 `信息汇总.xlsx`。**

---

## 3. 从源码运行 / 重新打包

> ⚠️ **解释器陷阱**：部分环境下 PATH 里的 `python` 不是标准 CPython（**缺 tkinter**）。
> 必须用标准 CPython：`py -3.13`（或本机标准 CPython 3.13 的完整路径）。
> 建好 venv 后统一从项目根目录执行 `.venv\Scripts\python.exe`。

```bat
:: 一次性环境
build\build_venv.bat

:: 绿色 exe（含 no-AI 静态门禁、图标、默认配置导出）
build\build_exe.bat

:: 安装向导（需 build\innosetup\ISCC.exe）
build\make_setup.bat

:: 源码启动
.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'src');from pdfrenamer.app import main;raise SystemExit(main())"
```

### 自检与测试

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.venv\Scripts\python.exe tests/scan_no_ai.py
.venv\Scripts\python.exe tests/ui_smoke.py
dist\PdfRenamer.exe --selftest       :: 打包后自检，报告写在 %TEMP%\pdfrenamer_selftest.txt
```

`--selftest` 会在临时目录生成一份中文合同 PDF，完整跑「提取 → 改名 → Excel → 撤销」，验证 frozen 环境里所有依赖确实可用。

---

## 4. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| GUI | 标准库 `tkinter/ttk` | 零第三方 GUI 依赖，打包最稳 |
| PDF | `PyMuPDF==1.26.7` | 中文 CID/ToUnicode 兼容最好、最快 |
| 备用后端 | `pypdf`、`pdfplumber` | 通过 `config.backend` 一行切换 |
| Excel | `openpyxl` | 纯 Python、MIT |
| 打包 | `PyInstaller 6.22.3` onefile + `Inno Setup 6.7.4` | 绿色 exe + 标准安装向导 |

**为什么锁 PyMuPDF 1.26.x**：2.x 会强制依赖 `onnxruntime`、`numpy`、`pymupdf-layout` 等推理库，既违反「不嵌 AI」，也会显著放大安装包。本项目已把推理库从构建环境中移除，`tests/scan_no_ai.py` 是强制构建门禁。

PDF 引擎以 `BasePdfExtractor` 抽象隔离，若后续要对外分发、规避 AGPL，把 `config.backend` 改为 `pdfplumber`(MIT) 即可，业务代码零改动。

---

## 5. 规则怎么配

- **合同类型闸门**（V1.1.1，优先级最高、文档级）：合同模式在字段提取前用纯规则判定是否合同文档；绩效评价报告/工作方案等判为 `not_contract`，不改名、Excel 标「非合同文档（不改名）」。可在「处理选项」关闭或调整阈值。
- **扫描件补文**（V1.1.2）：`no_text_layer` 时自动渲染前 2 页 + 末页，调 Windows 系统内置离线 OCR 取文字，再走同一套规则链。**物理层异常优先**——OCR 失败/缺语言包仍是 `no_text_layer`，绝不会被合同闸门误标成「非合同文档」。
- **优先级**：结构化来源（`structured.py`，仅当字段在「结构化来源」下拉里声明；读 PDF 元数据与首页版式）→ 正则（取第 1 个捕获组）→ 标签关键词（同行取值，容忍「（盖章）」等装饰；仅短标签行可向下取一行）→ 按类型启发式 → 填「未知」。
- **人工补录**：扫描预览表**双击任意行**即可手动填写 5 个字段，确认后会重新生成文件名并写入 Excel（标记「人工补录」），撤销链路不受影响。
- **V1.1.1 规则增强**：合同名称删掉误取元凶「项目名称」；补中文合同别称（委托单位/中标单位等）；支持中文数字与「年月无日」日期、叙述式金额（`合同总金额为123.4567 万元`）、跨行标签续值。配置自动从 v3 升到 **v5**（v3→v4→v5 链式），用户自定义正则/模板/字段不丢，升级前自动备份。
- **结构化来源**可选：`paper_title` / `paper_authors` / `paper_venue` / `paper_year`，或「不使用」。它仍是纯字符串匹配与正则，不含任何模型推理。
- **字段类型**：`text` 文本、`list` 多值（文件名只取第一作者）、`year` 年份、`company` 公司名（去盖章与地址电话噪声）、`date` 日期（→ `YYYY-MM-DD`）、`money` 金额（去千分位、万元换算为元）。
- **启发式命中**会在预览里标橙色，建议人工复核。
- 预设字段与默认正则见 `src/pdfrenamer/presets.py`，也可在界面直接改，改动自动保存。

> **V1.1.0 已完成真实样本校准**：`samples/user/` 下 6 篇真实英文论文 PDF 的 24 个字段命中率由 **12.5% 提升到 100%**（`tests/calibrate.py` 可复现，报告在 `output/calibration_*.json`）。拿到新的论文/合同版式时，仍建议在界面里调整关键词或正则后先看预览。
>
> **V1.1.2 真实合同扫描件校准**：`samples/user/` 下 4 份真实合同扫描件（CamScanner / Sharp，无文本层）经系统离线 OCR 后 **4/4 出文本、4/4 判为合同、4/4 正常改名**，字段命中 14/20 = 70%（`tests/calibrate_scanned.py` 可复现，期望值由人工逐页目视核对）。金额与签订日期多在正文中间页，默认只读前 2 页 + 末页，未命中属已知限制，可在预览表双击补录。
>
> 注意：软件**只处理目录下直属 `*.pdf`**；`samples/user/` 里另有 6 篇论文 PDF 用于论文模式校准。此前 3 份绩效评价报告与 2 份 Word 空白范本已由用户移除，等价负样本改由 `tests/make_samples.py` 合成，回归覆盖不丢。

---

## 6. 已知限制 / FAQ

| 问题 | 说明 |
|---|---|
| 扫描件能识别吗 | **能（V1.1.2）**：用 Windows 系统内置离线 OCR 识别前 2 页 + 末页。目标机需 Win10+ 且装有中文 OCR 语言包（本机已确认 `zh-Hans-CN` 可用）；缺语言包时保持原名并在 Excel 标「需人工处理」。识别不全可双击预览行手动补录。 |
| 这是「嵌入 AI」吗 | 不是。不含大模型 / 云端 API / 推理库，零联网、零新增 Python 依赖；只调用操作系统随附的传统 OCR 组件把图片转成文字，结果仍由关键词与正则确定性提取。 |
| 绩效评价报告被当合同改名了？ | V1.1.1 已加合同类型闸门，判 `not_contract` 后不改名并在 Excel 标记；如误杀真实合同，去「处理选项」关掉校验或调低阈值。 |
| 能只挑几个 PDF 处理吗 | 能。切到「单独选择 PDF 文件…」可多选，但须位于同一目录；Excel 仍输出到该目录，撤销/重名检测不变。 |
| 旧 Excel 会丢历史吗 | 不会。新增「PDF 类型」列时就地升列并按 A 列「模式」回填旧行，不备份、不重建；仅表头确实不兼容才备份重建。 |
| Word 合同（.doc/.docx）能处理吗 | 本期不能，只处理 `*.pdf`。如需直接处理 Word 请提出，属于需求扩展。 |
| 会递归子目录吗 | 默认只处理所选目录直属 PDF。 |
| 升级后旧配置会丢字段吗 | 不会。`config_version` 升至 3 时自动合并出厂预设的结构化来源与新关键词，保留用户正则、模板与自定义字段，并备份旧配置。 |
| Excel 正开着怎么办 | 保存会失败，结果已写入 `rows.jsonl`；关闭 Excel 后点「恢复上次结果」。 |
| 改错了能恢复吗 | 能。点「撤销上次重命名」，基于 `plan.json` 逆序还原；遇冲突跳过而非覆盖，任何情况都不删除文件。 |
| 数据会外传吗 | 不会。运行时零网络请求，PDF 内容不出本机。 |
| 杀软误报 | onefile 关闭 UPX、未加混淆；源码与构建脚本齐全，可自行复现。 |
| 许可证 | PyMuPDF 1.26.7 为 AGPL 3.0，当前默认构建与 OCR 页面渲染均依赖它；本项目仅内部自用且源码随仓库交付。**对外分发前需整体评估 AGPL 义务或商业许可**——仅把 `config.backend` 切到 pdfplumber(MIT) 不足以完全规避，因为扫描件 OCR 的页面渲染仍使用 PyMuPDF。 |

---

## 7. 交付物

- `dist/PdfRenamer.exe`、`dist/PdfRenamer_setup.exe`
- `docs/需求分析说明书.docx`、`docs/PRD产品需求文档.docx`
- `src/` 全源码、`config/default_config.json`、`assets/app.ico`
- `build/` 打包链路、`tests/` 样例与测试用例、`wheels/` 离线依赖
- `tests/acceptance_cases.md` 验收记录
- 开发工作日志（存放在开发机本地，不入库）

**版本**：1.1.2　|　**平台**：Windows 10 22H2+　|　**构建日期**：2026-11-15

---

## 8. 跨电脑开发（从 GitHub 克隆）

本仓库为**私有仓库**，克隆前需先完成 GitHub 认证：

```bat
gh auth login --hostname github.com --git-protocol https --web
git clone <仓库URL>
cd PdfRenamer
```

### 环境要求

- Windows 10 22H2 及以上；标准 CPython 3.13（**必须含 tkinter**）+ PowerShell 5.1。
- 扫描件 OCR 依赖系统内置离线中文语言包 `zh-Hans-CN`（设置 → 时间和语言 → 语言 → 中文添加「OCR」即可）；缺语言包时扫描件优雅降级，不影响其它功能。

### 常用命令（均在项目根目录执行）

```bat
build\build_venv.bat                                  :: 一次性：创建 .venv 并装依赖
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.venv\Scripts\python.exe tests/scan_no_ai.py         :: no-AI 静态门禁
.venv\Scripts\python.exe tests/ui_smoke.py
build\build_exe.bat                                   :: 构建绿色 exe（含门禁）
build\get_innosetup.bat                               :: 可选：获取便携 Inno Setup
build\make_setup.bat                                  :: 可选：构建安装向导
```

### 干净克隆中不存在的内容（均为本机生成或私有，不入库）

- `dist/`、`output/`、`wheels/`、`build/innosetup/`：构建与校准产物，由脚本在本机生成。
- `samples/user/`：**真实样本**（6 篇论文 + 4 份合同扫描件，含隐私），已被 `.gitignore` 排除。换机后需自行放置。
- `tests/scanned_expect.json`：真实扫描件的期望值（含真实机构/金额），仅存本机；格式见 `tests/scanned_expect.example.json`。缺它时 `tests/calibrate_scanned.py` 会输出 `[SKIP]` 并返回 0，不算失败。
- 涉及真实样本的个别 OCR 单测在干净克隆中会自动 skip，属预期行为。

### 真实样本使用纪律（务必遵守）

- 真实样本与真实期望值**禁止提交**（`.gitignore` 已排除，误提交也无法过审查）。
- 校准脚本对样本只读；校准报告（`output/calibration_*.json`）只留本机。
- `build/make_docs.py` 只生成 HTML（`output/html/`）；仓库中的两份 DOCX 已预生成入库，普通开发不依赖外部工具链。
