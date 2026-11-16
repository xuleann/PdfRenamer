# PdfRenamer 验收用例与实测记录

- 版本：1.1.2　|　日期：2026-11-15　|　平台：Windows 10 Pro 22H2 (19045)
- 解释器：项目根目录 `.venv\Scripts\python.exe`（标准 CPython 3.13.17，Tk 8.6.15）
- 样例：`tests/make_samples.py` 生成 **13 份**测试 PDF（含 3 份合成绩效评价报告负样本）；`samples/user/` 下 6 篇真实英文论文 PDF + **4 份真实合同扫描件（纯图片、无文本层）**。此前 3 份绩效评价报告与 2 份 Word 空白范本已由用户移除，等价负样本改由脚本合成。

## 自动化验证命令与结果

| 命令 | 结果 |
|---|---|
| `.venv\Scripts\python.exe tests/make_samples.py` | 生成 13 份样例 PDF（标准论文/合同、扫描件、加密件、字段缺失、非法字符超长、重名 A/B、全角标签独占行、备用论文、3 份合成绩效评价报告） |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | **69/69 通过，0 skip**（含 `test_ocr_winrt.py` 17 项、`test_manual_override.py` 6 项、负样本用例不再静默跳过） |
| `.venv\Scripts\python.exe tests/scan_no_ai.py` | **[PASS]** 扫描 25 个源文件，未发现 AI / 推理 / 网络调用依赖 |
| `.venv\Scripts\python.exe tests/ui_smoke.py` | **[PASS]** 主窗口、模式弹窗、双模式切换、扫描预览、执行、Excel、撤销全部通过 |
| `.venv\Scripts\python.exe tests/test_ui_files.py` | **[PASS] 3/3** 同目录多选全流程、跨目录拒绝、清空已选 |
| `.venv\Scripts\python.exe tests/test_manual_override.py` | **[PASS] 6/6** 补录重生成文件名、类型归一化、清空预览、双击映射、snap OCR 键、no-op |
| `.venv\Scripts\python.exe tests/calibrate.py --json output/calibration_after.json` | **24/24 = 100%**（6 篇真实英文论文，V1.1.0 校准不退化） |
| `.venv\Scripts\python.exe tests/calibrate_negative.py --json output/calibration_negative.json` | **[PASS] 3/3 判非合同、15/15 字段正确缺失、0 改名**（合成负样本） |
| `.venv\Scripts\python.exe tests/calibrate_scanned.py --json output/calibration_scanned.json` | **[PASS] 4/4 OCR 出文本、4/4 判为合同、4/4 正常改名、字段命中 14/20 = 70%** |
| `dist\PdfRenamer.exe --selftest` | **RESULT: PASS**（`PdfRenamer 1.1.2 selftest`；配置载入、提取、改名、Excel、撤销全链路） |
| `PdfRenamer_setup.exe /VERYSILENT` + 卸载 | 安装 ExitCode=0、卸载 ExitCode=0；安装版自检 PASS；与绿色版 SHA256 一致 |
| `SHA256(dist/PdfRenamer.exe)` | `A04A0DA0CC41D66411131E7DCFBCBEA454F6AA3D171177D2D07CF00FD7D26D30`（安装版内 exe 哈希一致） |

## V1.1.2 真实合同扫描件正向校准（4 份样本）

用户删除了上一轮误放的 3 份绩效评价报告，新放入 **4 份真实合同扫描件**（CamScanner / Sharp，纯图片、全文文本层 0 字符、元数据只有扫描时间）。期望值 `tests/scanned_expect.json` 由人工逐页目视核对抄录。

| 样本 | OCR 字符 | 判定 | 合同名称 / 甲方 / 供方 | 时间 | 金额 |
|---|---|---|---|---|---|
| 扫描样本 A | 847 | 合同 | 3/3 命中 | 未取到（末页手写） | 未取到（正文中间页） |
| 扫描样本 B | 1511 | 合同 | 3/3 命中 | 2024（年份） | 未取到（正文中间页） |
| 扫描样本 C | 2274 | 合同 | 3/3 命中 | 未取到 | 金额命中（首页合同价格） |
| 扫描样本 D | 2119 | 合同 | 3/3 命中 | 未取到 | 未取到（正文中间页） |

**合计 4/4 OCR 出文本、4/4 判为合同、4/4 正常改名、字段命中 14/20 = 70%、0 垃圾文件名**。未命中项集中在正文中间页的金额/签订日期——默认只 OCR 前 2 页 + 末页以控制耗时（每份 1.5–2.3 秒），属已知限制，可在预览表双击该行人工补录。

> 说明：软件不放「训练」，本轮提升来自新增 `extractor/ocr_winrt.py`（Windows 系统内置离线 OCR）+ 规则防护 + 人工补录，全部随 exe 分发。OCR 不是大模型、不联网、零新增 Python 依赖。4 份样本全程只读，大小与时间戳未变。

## V1.1.1 合同模式负样本校准（历史记录，样本已移除）

上一轮的 3 份 PDF 经逐页核对**不是合同**，而是财政支出绩效评价报告：封面为 `项目名称/项目单位/委托单位/评价机构/成文年月`，全文无甲乙双方、签订日期、合同金额的标签-值对。旧规则会把 `项目名称：` 误取为合同名称。

**合计 3/3 判非合同、15/15 字段缺失、0 改名**。V1.1.2 起这 3 份真实文件已由用户删除，等价负样本改由 `tests/make_samples.py` 合成（`11_/12_/13_绩效评价*.pdf`），回归覆盖不依赖用户样本，仍为 3/3 + 15/15 + 0 改名。

## 验收用例清单（对应 PRD 第 13 节）

| # | 用例 | 结果 | 证据 |
|---|---|---|---|
| 1 | 启动后可选择论文/合同两种模式，且可记住选择 | 通过 | `ui_smoke.py`：模式选择弹窗构建成功；`config.remember_mode` 持久化 |
| 2 | 自定义字段 + 正则重启后仍在 | 通过 | `test_core.PipelineTests` + `config.load_config/save_config` 原子写与 deep_merge |
| 3 | 论文 4 个预设字段正确提取 | 通过 | `test_paper_fields`：作者、期刊、年份；`test_calibration.StructuredTests` |
| 4 | 合同「甲方（盖章）」+ 金额 + 日期归一化 | 通过 | `test_contract_fields`：`2024年3月5日`→`2024-03-05`，`¥1,200,000.00元`→`1200000.00元` |
| 5 | 正则未命中时回退关键词 | 通过 | `engine._field_result` 优先级链；`test_fullwidth_label_on_own_line` |
| 6 | 缺失填「未知」并标浅黄 | 通过 | `test_missing_fields`；`excel.py` `_MISS_FILL` |
| 7 | 非法字符 / 超长 / 重名 / 大小写去重 | 通过 | `test_filename`、`test_unique`、`test_rename_and_excel` |
| 8 | 扫描件不改名且 Excel 标红 | 通过 | `test_scanned_pdf`、`test_rename_and_excel`（这两项在关闭 OCR 的自造样例上断言 V1.1.1 行为；真实扫描件改由 #35 覆盖自动识别） |
| 9 | 加密 PDF 不改名并标记 | 通过 | `test_encrypted_pdf` → `DOC_ENCRYPTED` |
| 10 | Excel 固定生成在所选目录，含冻结首行与自动筛选 | 通过 | `test_rename_and_excel`：`A2` 冻结、`auto_filter.ref` 非空 |
| 11 | 已存在 Excel 时按模式分 sheet 追加，旧数据不丢 | 通过 | `test_excel_append_preserves_old_rows` |
| 12 | 一键撤销后原文件名完整恢复、零文件丢失 | 通过 | `test_undo_restores_all`、`ui_smoke.py` |
| 13 | 撤销冲突时不覆盖、不删除 | 通过 | `undo.py`：src 已存在则跳过；全程只用 `os.rename` |
| 14 | 中途崩溃后可用「恢复上次结果」补写 Excel | 通过 | `test_rows_jsonl_recovery`（`recover_rows` 已兼容旧 jsonl 缺类型键） |
| 15 | `scan_no_ai.py` 通过，运行时零外网请求 | 通过 | 静态门禁 24 文件 + `requirements.txt` 白名单；venv 中 `onnxruntime` 为 False |
| 16 | `dist/PdfRenamer.exe --selftest` 返回 PASS | 通过 | `%TEMP%/pdfrenamer_selftest.txt`：`PdfRenamer 1.1.2 selftest` / `RESULT: PASS` |
| 17 | `setup.exe` 可完成向导安装与卸载 | 通过 | Inno Setup 6.7.4 编译；静默安装/卸载 ExitCode=0；简体中文字语言包 |
| 18 | 所有产物位于项目目录内，原始需求文件未被改动 | 通过 | 最终目录核查；需求文件仅被读取 |
| 19 | 6 篇真实英文论文 24 个字段命中率 ≥ 95% | 通过 | 实测 24/24 = 100%；`output/calibration_before.json` → `calibration_after.json` |
| 20 | 2 份中文空白合同范本不误取正文、空白占位判缺失 | 通过 | 转 PDF 后逐字段核对；`test_calibration.PlaceholderTests` |
| 21 | 旧 config 升级到 v3 后论文字段获得结构化来源且用户字段不丢 | 通过 | `test_calibration.MigrationTests.test_v2_config_gets_source_and_new_keywords` |
| 22 | 3 份绩效评价报告判 `not_contract`、5 字段全缺失、不改名 | 通过 | `test_negative.NegativeSampleTests`；`output/calibration_negative.json` |
| 23 | 非合同报告不因 `项目名称：` 误取合同名称 | 通过 | `presets.py` 删除同义词 + 闸门 SKIP 双保险；负样本断言 |
| 24 | 自造合同样例闸门不误杀、26 项原有单测不退化 | 通过 | 全量 44/44；`ContractGateTests.test_real_contract_passes` |
| 25 | 中文数字日期与叙述式金额 | 通过 | `二〇一八年十一月`→`2018-11`；`合同总金额为123.4567 万元`→`1234567元`；`test_date`/`test_money` 不退化 |
| 26 | 跨行标签值合并，括号别名空白仍返回空 | 通过 | `test_negative.NewRuleTests` 两项 |
| 27 | 多选 PDF（同目录）只处理选中项、Excel 在该目录、可撤销 | 通过 | `test_ui_files.test_same_directory_select_two_and_process` |
| 28 | 多选 PDF（跨目录）被拒且无任何副作用 | 通过 | `test_ui_files.test_cross_directory_is_rejected` |
| 29 | 文件夹模式默认路径零回归 | 通过 | `ui_smoke.py` 全过；`cfg.last_dir` 链路不变 |
| 30 | Excel 末列「PDF 类型」+ 类型配色，A1 仍「模式」 | 通过 | `test_rename_and_excel` 新增表头与 A 列断言 |
| 31 | 旧 Excel 无损升列（历史行保留、无备份重建） | 通过 | `test_excel_upgrade_adds_type_column` |
| 32 | config v3→v4 迁移：备份、清理误取词、追加别名、保留用户资产 | 通过 | `test_calibration.MigrationTests.test_v3_to_v4_migration` |
| 33 | 现代浅色主题在 selftest / ui_smoke / frozen 三处不报错 | 通过 | `clam` 生效、Accent 按钮、斑马纹、状态栏、窗口图标；`--selftest` 不创建窗口 |
| 34 | 版本 1.1.1 全位置一致，V1.1.0 历史叙述保留 | 通过 | 历史记录；V1.1.2 已全位置同步 |
| 35 | 4 份真实合同扫描件 4/4 OCR 出文本、4/4 判为合同、4/4 正常改名 | 通过 | `tests/calibrate_scanned.py`；`output/calibration_scanned.json` |
| 36 | 扫描件字段命中 14/20 = 70%，0 垃圾文件名 | 通过 | 同上；合同名称/甲方/供方 12/12 全中，金额/日期受页数限制 |
| 37 | OCR 关闭时退回 V1.1.1 行为 | 通过 | `test_core.test_scanned_pdf`；引擎 `scan_ocr_enabled=False` 实测 `no_text_layer` + skipped |
| 38 | OCR 语言包缺失 / 超时 / 渲染异常优雅降级，`no_text_layer` 优先于合同闸门 | 通过 | `test_ocr_winrt.py` 17 项（mock 降级/超时/编码/清理）；引擎闸门改 `(ok, partial)` 白名单 |
| 39 | 临时 PNG 只落系统 TEMP 且用完即删，样本零改动 | 通过 | `test_ocr_winrt.test_temp_png_cleaned`；10 个样本 SHA256 + 大小 + 时间戳前后一致 |
| 40 | 汉字间伪空格归一化，OCR 文本可命中既有正则 | 通过 | `test_ocr_winrt.SpacingTests`：「甲 方 ：」→「甲方:」 |
| 41 | 扫描件 metadata 清空，扫描时间不被当成题目/日期 | 通过 | `test_ocr_winrt.test_supplement_ok` 断言 `metadata == {}` |
| 42 | 金额噪声防护：「支付合同金额的 25%」不取为总价 | 通过 | 引擎 `_money_ratio_guard`；实测继续命中页面上的真实合同价格 |
| 43 | 日期噪声防护：OCR 错字无年份数字时判缺失 | 通过 | `rules.normalize_date` 末尾校验；实测「戔为炀一」不再进文件名 |
| 44 | 合同名称启发式不取「合同编号」或正文句子碎片 | 通过 | `_CONTRACT_LABEL_NOISE` + `_TITLE_SENTENCE`；4/4 扫描件名称合理 |
| 45 | 人工补录：双击预览行填 5 字段后 skipped → planned | 通过 | `test_manual_override.py` 6/6；值按类型归一化、Excel/plan.json 标「人工补录」 |
| 46 | 清空预览后补录值清除；无补录时 no-op | 通过 | `test_clear_preview_drops_overrides`、`test_no_overrides_is_noop` |
| 47 | UI 文案级精简：1180×760 / 最小 1040×680 / 日志 5 行 / 预览 8 行 / 帮助菜单含规则说明 | 通过 | 源码核查 + `ui_smoke.py` PASS；不删控件、不改名变量 |
| 48 | `ui_smoke` / `test_ui_files` 3 项 / 补录 6 项 / 全量 69 项全绿且 0 skip | 通过 | 负样本改由合成 PDF 覆盖，`test_negative.NegativeSampleTests` 不再静默跳过 |
| 49 | config v4→v5：用户显式关闭的 `scan_ocr_enabled` 不被覆盖；v3→v5 链式迁移 | 通过 | `test_calibration.test_v4_to_v5_migration` / `test_v3_to_v5_chain` |
| 50 | `requirements.txt` / `PdfRenamer.spec` / `scan_no_ai.py` 零改动，零新增 Python 依赖 | 通过 | 文件对比；no-AI 门禁 25 文件 PASS |
| 51 | UI 测试不污染用户 `%APPDATA%/config.json` | 通过 | `ui_smoke.py` 屏蔽 `save_config` 并固定 folder 模式；复跑后配置仍为 `last_input_mode=folder`、`last_dir=""` |
| 52 | 版本 1.1.2 全位置一致，setup.exe 静默安装/卸载、SHA256 一致 | 通过 | 全局版本号核查 + 安装实测（哈希见文末） |

## 已知限制（非缺陷，已在需求/PRD 中声明）

- 扫描件 OCR 默认只读前 2 页 + 末页；正文中间页的金额/签订日期可能取不到 → 预览表双击人工补录。
- 目标机需 Windows 10 22H2+ 且装有中文 OCR 语言包（`zh-Hans-CN`）；缺语言包时保持原名并标「需人工处理」。
- OCR 对印章、手写体、竖排与错字识别率有限；启发式命中建议预览复核后再执行。
- 只处理 `*.pdf`，不递归子目录；`.doc`/`.docx` 不在本期范围。
- 「单独选择 PDF 文件」限制同一目录；跨目录需按目录分批处理（后续迭代）。
- 「已选文件列表」控件本期未做，用计数文案 + 清空按钮代替。
- `samples/user/` 放更多样本**不会**自动提升效果（软件不嵌 AI、无训练环节）；规则改进需改代码并重新打包。
- `信息汇总.xlsx` 若正被 Excel 打开，保存会失败 → 关闭后用「恢复上次结果」补写。

## 构建产物

- `dist/PdfRenamer.exe` 与 `dist/PdfRenamer_setup.exe`：均为 1.1.2（安装版内 exe 与绿色版一致）。
- `SHA256(dist/PdfRenamer.exe)`：`A04A0DA0CC41D66411131E7DCFBCBEA454F6AA3D171177D2D07CF00FD7D26D30`（安装版内 exe 哈希一致）
