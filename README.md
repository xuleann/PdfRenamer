# PdfRenamer — 本地 PDF 信息提取与批量更名工具

一款**纯本地、零联网**的 Windows 桌面软件：选一个文件夹，提取 PDF 关键信息，生成带手写原图的**复核表**，人工复核确认后再按模板批量重命名，并在所选目录生成 `信息汇总.xlsx`。

支持**论文 / 合同**两种模式；合同模式面向**劳动合同 / 劳务合同**，自动提取乙方、身份证号、合同起止日期、签订日期、用工部门等 7 项信息。

> **"零联网、非大模型"**：软件不调用任何云端 API、不含大语言模型，PDF 内容不出本机。信息提取依靠 PDF 文本层 + 关键词与正则的确定性解析。对**无文本层或手写字段**的扫描件，使用内置的本地离线 OCR（`Windows.Media.Ocr` 系统 OCR + RapidOCR 手写识别，均为本机推理、零联网）。

> **V1.6.5 当前版本**：扫描导出复核表 → 人工对照手写原图复核 → 按复核表改名；六字段截图、翻转页自动转正、OCR 提速（检测次数降约 22%）。详见下方「版本记录」。

---

## 1. 直接使用（无需 Python）

| 文件 | 说明 |
|---|---|
| `dist/PdfRenamer.exe` | 绿色单文件，双击即用，不写注册表 |
| `dist/PdfRenamer_setup.exe` | 带安装向导的安装包，可创建桌面快捷方式、可从「添加/删除程序」卸载 |

首次启动会让你选择 **论文** 或 **合同** 模式；勾选「记住本次选择」后下次直接进入，也可随时从「模式」菜单切换。

### 合同模式操作四步（v1.6.0 起的新流程）

1. **选择要处理的 PDF**：默认「整个文件夹」，点「浏览…」选合同所在目录（只处理直属 PDF，不递归子目录）；也可切到「选择 PDF 文件（同目录）」一次勾选多个文件（**须位于同一目录**）。
2. **① 扫描并导出复核表**：后台逐份提取信息并做六字段手写截图，在文件所在目录生成 `信息汇总.xlsx`。**此步不改动任何 PDF 文件**，改名还没发生。
3. **人工复核（关键）**：打开 `信息汇总.xlsx`，对照每行的手写原图，直接修改「（复核）」结果列，改完**保存并关闭 Excel**。这一步是正式改名前的最后把关。
4. **② 按复核表改名**：软件读取你改过的 Excel，用表里的值生成文件名并原地改名；同时只更新「新文件名」列，**不覆盖你复核过的字段值**。改错了点「撤销上次重命名」可完整还原。

- 耗时参考：电子版约 1~2 秒/份；扫描件（需图像识别）约 3~10 秒/份。
- 扫描件、加密件、乱码件、被判为非合同的文件**不会改名**，会在 Excel 标红说明原因。
- 「恢复上次结果」：Excel 正被打开导致写入失败时，关闭 Excel 后点它即可从增量日志补写。

### 论文模式

论文模式提取论文题目、作者、期刊、年份等字段并批量改名，可**双击预览行人工补录**；流程与旧版一致（扫描预览 → 确认执行）。论文 PDF 的元数据与首页版式解析由 `structured.py` 纯规则完成。

---

## 2. 复核表怎么用（合同模式重点）

`信息汇总.xlsx` 每行对应一份合同。**六个手写字段各占两列**：第一列「字段（复核）」是可修改的文字结果，第二列「字段（识别结果）」是该字段的原件截图（供对照，不用改，也不能在 Excel 里编辑）。

| 字段对 | 截图来源 |
|---|---|
| 乙方（复核）/ 乙方（识别结果） | 第 1 页手写姓名原图 |
| 身份证号（复核）/ 身份证号（识别结果） | 身份证号手写区原图 |
| 开始日期（复核）/ 开始日期（识别结果） | 「合同期限」标题下方整行原图（起止两个日期都在图里） |
| 结束日期（复核）/ 结束日期（识别结果） | 同上同一整行原图 |
| 签订日期（复核）/ 签订日期（识别结果） | 末页签章区落款日期原图 |
| 用工部门（复核）/ 用工部门（识别结果） | 「第二条第二点」高清原图 |

- **默认值改名格式**：`劳动合同_2023_01_张三.pdf`，即 `合同类型_签订年份_序号_乙方姓名.pdf`；序号每批从 01 开始，同名自动加 `_2` 不覆盖。
- **xxN 占位**：手写姓名机器认不准时，乙方结果列显示 `xx1`、`xx2`…… 提示待核对；对照原图改成正确姓名后再改名。若保留 xxN，文件名里也会用 xxN，方便事后识别。
- **不依赖红框**：测试 PDF 上的红框只是给人看的标注，软件**完全不读取红框**，靠 OCR 文字 + 关键词（合同期限、身份证号、部（室）等）定位。实测同一份合同「有红框 / 无红框」六个字段提取结果完全一致。
- **自动提取 7 项**：合同类型（劳动/劳务）、乙方、身份证号（15/18 位）、开始日期、结束日期、签订日期、用工部门（七选一：办公室/财务室/交通/物业/服务一部/服务二部/资产）。

---

## 3. 目录结构

```
PdfRenamer/（项目根目录，可克隆到任意路径）
├─ dist/PdfRenamer.exe              绿色单文件
├─ dist/PdfRenamer_setup.exe        安装向导
├─ docs/需求分析说明书.docx         需求分析
├─ docs/PRD产品需求文档.docx        PRD 拆解
├─ docs/PdfRenamer使用说明手册_v1.4.8.docx  使用说明手册
├─ 使用说明.txt                     最新版（v1.6.5）简明使用说明
├─ src/pdfrenamer/                 全部源码
│  ├─ app.py / __main__.py         入口（含 --selftest）
│  ├─ models.py / presets.py       数据模型、两套模式出厂预设
│  ├─ rules.py / config.py         清洗归一化、配置持久化（v8 链式迁移）
│  ├─ structured.py                ★论文 PDF 元数据 + 首页版式解析（纯规则）
│  ├─ contract_gate.py             ★合同文档类型闸门（纯规则）
│  ├─ review.py                    ★复核占位符分配与读回
│  ├─ extractor/
│  │  ├─ ocr_winrt.py              ★Windows 系统内置离线 OCR 补文（零新增依赖）
│  │  ├─ ocr_rapid.py              ★RapidOCR 手写识别 + 页方向校正 + OCR 页缓存
│  │  ├─ field_crop.py             ★六字段手写截图定位与裁剪
│  │  └─ pdf backend              pymupdf / pypdf / pdfplumber
│  ├─ engine.py / renamer.py       提取引擎、重命名引擎
│  ├─ undo.py / excel.py           还原日志、复核表/汇总 Excel 读写
│  └─ ui/                          tkinter 界面（模式选择 / 主窗口 / 字段编辑器 / theme）
├─ src/launcher.py                 PyInstaller 入口（绝对导入）
├─ config/default_config.json      出厂预设（打包进 exe）
├─ assets/app.ico                  图标
├─ build/                          spec、bat、Inno Setup .iss、图标/文档生成脚本
├─ tests/                          单元测试、UI 冒烟、合规扫描、校准脚本
│  └─ samples/                     合同/论文样本 PDF **不入库**，需运行 tests/make_samples.py 本地生成
├─ samples/user/                   真实样本（仅本机，已在 .gitignore 中排除）
├─ output/html/                    文档排版 HTML 中间产物
├─ wheels/                         离线 wheel 兜底
└─ requirements.txt / README.md
```

配置与日志写在 `%APPDATA%/PdfRenamer/`（`config.json`、`plans/`、`rows/`）。
**唯一写进用户所选目录的文件是 `信息汇总.xlsx`。**

---

## 4. 从源码运行 / 重新打包

> ⚠️ **解释器陷阱**：部分环境下 PATH 里的 `python` 不是标准 CPython（**缺 tkinter**）。
> 必须用标准 CPython：`py -3.13`（或本机标准 CPython 3.13 的完整路径）。
> 建好 venv 后统一从项目根目录执行 `.venv\Scripts\python.exe`。

```bat
:: 一次性环境
build\build_venv.bat

:: 绿色 exe（含 no-AI/无云端依赖静态门禁、图标、默认配置导出）
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

## 5. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| GUI | 标准库 `tkinter/ttk` | 零第三方 GUI 依赖，打包最稳 |
| PDF | `PyMuPDF==1.26.7` | 中文 CID/ToUnicode 兼容最好、最快 |
| 备用后端 | `pypdf`、`pdfplumber` | 通过 `config.backend` 一行切换 |
| 系统 OCR | `Windows.Media.Ocr` | Win10/11 内置离线印刷体 OCR，零新增依赖 |
| 手写 OCR | `RapidOCR==3.10.0`（ONNX Runtime，本地推理） | 识别手写姓名/身份证/日期/部门，零联网 |
| Excel | `openpyxl` | 纯 Python、MIT |
| 打包 | `PyInstaller 6.22.3` onefile + `Inno Setup 6.7.4` | 绿色 exe + 标准安装向导 |

**为什么锁 PyMuPDF 1.26.x**：2.x 会强制依赖 `onnxruntime`、`numpy`、`pymupdf-layout` 等推理库，显著放大安装包且破坏确定性构建。`tests/scan_no_ai.py` 是静态构建门禁，禁止 `torch/transformers/openai/requests` 等**大模型 / 云端 API / 网络客户端**进入源码运行时；RapidOCR 与系统 OCR 均为**本地离线识别**，不涉及云端或大模型，不在此列。

PDF 引擎以 `BasePdfExtractor` 抽象隔离，若后续要规避 AGPL，把 `config.backend` 改为 `pdfplumber`(MIT) 即可，业务代码零改动。

---

## 6. 规则怎么配

- **合同类型闸门**（优先级最高、文档级）：合同模式在字段提取前用纯规则判定是否合同文档；绩效评价报告/工作方案等判为 `not_contract`，不改名、Excel 标「非合同文档（不改名）」。可在「处理选项」关闭或调整阈值。
- **扫描件补文**：`no_text_layer` 时自动渲染前几页 + 末页，先调 Windows 系统内置离线 OCR 取文字；手写字段再用 RapidOCR 局部放大识别。**物理层异常优先**——OCR 失败/缺语言包仍是 `no_text_layer`，绝不会被合同闸门误标成「非合同文档」。
- **手写字段定位**：靠 OCR 文字 + 关键词锚点定位（合同期限、身份证号、部（室）等），不依赖 PDF 上的任何人工红框标记；页面若被旋转 90/180/270° 会自动转正后再识别。
- **优先级**：结构化来源（`structured.py`，仅当字段在「结构化来源」下拉里声明）→ 正则（取第 1 个捕获组）→ 标签关键词（同行取值，容忍「（盖章）」等装饰；短标签行可向下取一行）→ 按类型启发式 → 填「未知」。
- **字段类型**：`text` 文本、`list` 多值（文件名只取第一作者）、`year` 年份、`company` 公司名（去盖章与地址电话噪声）、`date` 日期（→ `YYYY-MM-DD`）、`money` 金额（去千分位、万元换算为元）。
- **配置升级**：`config_version` 升至 **v8**（链式迁移），用户自定义正则/模板/字段不丢，升级前自动备份。
- 预设字段与默认正则见 `src/pdfrenamer/presets.py`，也可在界面直接改，改动自动保存。

> **V1.1.0 真实论文校准**：`samples/user/` 下 6 篇真实英文论文 PDF 的 24 个字段命中率由 12.5% 提升到 100%（`tests/calibrate.py` 可复现）。
>
> **真实合同扫描件**：多份真实合同扫描件经本地 OCR 后完成字段提取；「有红框 / 无红框」结果一致。校准脚本 `tests/calibrate_scanned.py` 可复现，期望值文件 `tests/scanned_expect.json` 仅存本机。

---

## 7. 已知限制 / FAQ

| 问题 | 说明 |
|---|---|
| 扫描件能识别吗 | **能**：系统内置离线 OCR + RapidOCR 手写识别，全在本机。目标机需 Win10+ 且装中文 OCR 语言包（`zh-Hans-CN`）；缺语言包时优雅降级为需人工处理。识别不全可在复核表对照截图补录。 |
| 这是「嵌入 AI / 上传合同」吗 | 不是。不含大语言模型、不调用云端 API、不联网；只有本地传统 OCR 把图片转成文字，结果仍由关键词与正则确定性提取。 |
| 扫描后没改名，是不是坏了 | 不是。v1.6.0 起扫描只生成复核表、不改文件；复核 Excel 后点「② 按复核表改名」才会真正改名。 |
| 为什么在 Excel 里改，不在软件里改 | Excel 里能同时看到识别结果和手写原图，对照改最直观；改完由软件读回，确保最终文件名就是核对过的内容。 |
| 我在 Excel 改了值，改名没生效 | 请确认已保存并关闭 Excel 后再点「② 按复核表改名」；值被 Excel 自动转成日期格式时软件也能正确读回。 |
| 软件依赖 PDF 上的红框标记吗 | 完全不依赖。红框只是给人看的标注；实测有红框 / 无红框提取结果一致。 |
| 画像页是翻转的，还能识别吗 | v1.6.4 起页面方向自动检测与校正，旋转 90/180/270° 的页面会先转正再识别。 |
| 用工部门识别为空或看不清 | 部门为七选一；对照「用工部门（识别结果）」高清列看手写笔画，在复核列填正确部门。 |
| 绩效评价报告被当合同改名了？ | 已加合同类型闸门，判 `not_contract` 后不改名并在 Excel 标记；如误杀真实合同，去「处理选项」关掉校验或调低阈值。 |
| 能只挑几个 PDF 处理吗 | 能。切到「选择 PDF 文件（同目录）」可多选，但须位于同一目录；Excel 仍输出到该目录。 |
| 旧 Excel 会丢历史吗 | 一般不会（新增列时就地升列）；仅表头确实不兼容（如结果列从纯字段名改为「（复核）」）才备份重建，旧表留档不丢。 |
| Word 合同（.doc/.docx）能处理吗 | 本期不能，只处理 `*.pdf`。 |
| 会递归子目录吗 | 默认只处理所选目录直属 PDF。 |
| Excel 正开着怎么办 | 保存会失败，结果已写入 `rows.jsonl`；关闭 Excel 后点「恢复上次结果」。 |
| 改错了能恢复吗 | 能。点「撤销上次重命名」，基于 `plan.json` 逆序还原；遇冲突跳过而非覆盖，任何情况都不删除文件。 |
| 数据会外传吗 | 不会。运行时零网络请求，PDF 内容不出本机。 |
| 杀软误报 | onefile 关闭 UPX、未加混淆；源码与构建脚本齐全，可自行复现。 |
| 许可证 | PyMuPDF 1.26.7 为 AGPL 3.0，当前默认构建与 OCR 页面渲染均依赖它；本项目内部自用且源码随仓库交付。**对外分发前需整体评估 AGPL 义务或商业许可**——仅把 `config.backend` 切到 pdfplumber(MIT) 不足以完全规避，因为扫描件 OCR 的页面渲染仍使用 PyMuPDF。 |

---

## 8. 交付物

- `dist/PdfRenamer.exe`、`dist/PdfRenamer_setup.exe`
- `docs/需求分析说明书.docx`、`docs/PRD产品需求文档.docx`、`docs/PdfRenamer使用说明手册_v1.4.8.docx`、`使用说明.txt`（v1.6.5）
- `src/` 全源码、`config/default_config.json`、`assets/app.ico`
- `build/` 打包链路、`tests/` 样例与测试用例、`wheels/` 离线依赖
- `tests/acceptance_cases.md` 验收记录
- 开发工作日志（存放在开发机本地，不入库）

**版本**：1.6.5　|　**平台**：Windows 10 22H2+　|　**最近更新**：2026-11-27

---

## 9. 版本记录

| 版本 | 主要变化 |
|---|---|
| v1.6.5 | 修复横放审批表页导致身份证/部门截图错位；复核表头改为「字段（复核）」+「字段（识别结果）」；扫描 OCR 提速（检测次数降约 22%） |
| v1.6.4 | 页面方向自动检测与校正（翻转页转正）；页级 OCR 缓存让截图复用提取结果，单份耗时约减半 |
| v1.6.3 | 按红框示例重做日期截图：开始/结束截「合同期限」标题下方整行，签订日期截末页落款行 |
| v1.6.2 | 日期截图先定位「合同期限」标题行，排除别处日期干扰 |
| v1.6.1 | 末页符号约定（-1=末页）、OCR 负向关键词 |
| v1.6.0 | 新工作流：扫描只出复核表、人工复核后再按表改名；六字段截图一次完成 |
| v1.5.0 | 六字段手写截图；序号每批从 01 开始 |
| v1.4.9 | 乙方/用工部门展开为「文字列 + 原件图列」 |
| v1.4.8 | 手写体识别与合同字段定位系统化 |
| v1.2.0 | 引入 RapidOCR 本地手写识别（可选依赖，纯离线） |
| v1.1.2 | 系统内置离线 OCR；预览表双击人工补录 |
| v1.1.1 | 合同类型闸门；界面单选/多选 PDF；浅色主题；`PDF 类型` 列 |
| v1.1.0 | 真实论文样本字段命中率校准 12.5% → 100% |

---

## 10. 跨电脑开发（从 GitHub 克隆）

本仓库为**私有仓库**，克隆前需先完成 GitHub 认证：

```bat
gh auth login --hostname github.com --git-protocol https --web
git clone <仓库URL>
cd PdfRenamer
```

### 环境要求

- Windows 10 22H2 及以上；标准 CPython 3.13（**必须含 tkinter**）+ PowerShell 5.1。
- 扫描件 OCR 依赖系统内置离线中文语言包 `zh-Hans-CN`（设置 → 时间和语言 → 语言 → 中文添加「OCR」即可）；缺语言包时扫描件优雅降级，不影响其它功能。
- RapidOCR 及其模型为本地离线推理，打包时已内置；源码运行需 `pip install -r requirements.txt`。

### 常用命令（均在项目根目录执行）

```bat
build\build_venv.bat                                  :: 一次性：创建 .venv 并装依赖
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.venv\Scripts\python.exe tests/scan_no_ai.py         :: 无云端/大模型依赖静态门禁
.venv\Scripts\python.exe tests/ui_smoke.py
build\build_exe.bat                                   :: 构建绿色 exe（含门禁）
build\get_innosetup.bat                               :: 可选：获取便携 Inno Setup
build\make_setup.bat                                  :: 可选：构建安装向导
```

### 干净克隆中不存在的内容（均为本机生成或私有，不入库）

- `dist/`、`output/`、`wheels/`、`build/innosetup/`：构建与校准产物，由脚本在本机生成。
- `samples/user/`：**真实样本**（论文 + 合同扫描件，含隐私），已被 `.gitignore` 排除。换机后需自行放置。
- `tests/scanned_expect.json`：真实扫描件的期望值（含真实机构/金额），仅存本机；格式见 `tests/scanned_expect.example.json`。缺它时 `tests/calibrate_scanned.py` 会输出 `[SKIP]` 并返回 0，不算失败。
- 涉及真实样本的个别 OCR 单测在干净克隆中会自动 skip，属预期行为。

### 真实样本使用纪律（务必遵守）

- 真实样本与真实期望值**禁止提交**（`.gitignore` 已排除，误提交也无法过审查）。
- 校准脚本对样本只读；校准报告（`output/calibration_*.json`）只留本机。
- `build/make_docs.py` 只生成 HTML（`output/html/`）；仓库中的 DOCX 已预生成入库，普通开发不依赖外部工具链。
