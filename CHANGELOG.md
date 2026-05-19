# 更新日志

本项目遵循语义化版本思路管理变更。正式版本以 Git tag 和 GitHub Release 为准。

## 未发布

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
