# 更新日志

本项目遵循语义化版本思路管理变更。正式版本以 Git tag 和 GitHub Release 为准。

## 未发布

- 暂无。

## v1.2.0 - 2026-05-21

### 改进

- 主窗口调整为“左侧文件/状态/队列侧栏 + 右侧结果视图”的双栏布局，减少纵向堆叠并提升宽屏使用效率。
- 分析、筛选、重复处理、导出等操作区改为更紧凑的两行工具栏，降低结果表上方空间占用。
- 文件队列改为随侧栏高度自适应，便于查看较多待处理 PDF。
- 统一侧栏卡片、结果表、按钮、进度条和列表的视觉样式，提升界面对比度和可读性。

### 验证

- `./.venv/bin/python -m compileall main.py source tests`
- `./.venv/bin/python -m unittest discover -s tests`

## v1.1.0 - 2026-05-20

### 新增

- 自动 OCR 复核流程：当 PDF 文本层缺字段、版式错序或疑似串字段时，自动触发 OCR 复核和字段补全。
- PDF 文本与 OCR 核心字段冲突标记，便于人工复核高风险记录。
- 红字发票负数金额解析与校验支持。
- 交错排列的购买方 / 销售方名称解析增强。
- 导出后可选择立即打开生成的 Excel 文件。
- 新增 GitHub PR / Issue 模板和仓库管理说明。

### 改进

- Excel “问题汇总”识别范围增加“不一致”“需复核”等高风险提示。
- 主界面布局、筛选区、日志页和状态摘要可读性增强。
- README 补充自动 OCR 复核和测试覆盖说明。
- `.gitignore` 明确排除本地运行输出目录。

### 验证

- `.venv/bin/python -m compileall main.py source tests`
- `.venv/bin/python -m unittest discover -s tests`
