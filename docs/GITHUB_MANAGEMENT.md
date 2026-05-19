# GitHub 内页与仓库管理说明

GitHub 仓库内页主要由 `README.md`、Issues / Pull Request 模板、Actions、Releases 和仓库 About 信息共同组成。本文件用于统一维护规则。

## 首页内容

- `README.md` 是仓库首页，面向新用户说明项目用途、功能、启动、测试、打包和发布方式。
- 功能变化、运行方式变化、支持平台变化时，应同步更新 `README.md`。
- 截图文件放在 `source/assets/`，README 只引用仓库内可追踪图片。
- 不在 README 中直接链接本地路径、虚拟环境或临时导出文件。

## 仓库 About 信息

建议在 GitHub 仓库右侧 About 区域维护：

- Description：`Desktop app for organizing PDF invoices locally, extracting key fields, deduplicating entries, and exporting Excel.`
- Topics：`python`、`qt`、`pyqt`、`pdf`、`invoice`、`ocr`、`excel-export`、`desktop-app`、`macos`、`windows`
- Website：如暂无官网或文档站，保持为空即可。

## Pull Request 管理

- 所有功能变更先走 PR，不直接推送到 `main`。
- PR 标题建议格式：`[codex] 简短说明`。
- PR 内容应说明：变更内容、影响范围、验证方式、发布注意事项。
- 若 PR 中包含 OCR、批量删除、移动文件、覆盖导出等高风险流程，应明确写出安全边界和人工确认点。
- 合并前至少确认 CI 通过，必要时补充手动截图或真实 PDF 验证结果。

## Issue 管理

- Bug 反馈使用 `.github/ISSUE_TEMPLATE/bug_report.yml`。
- 功能建议使用 `.github/ISSUE_TEMPLATE/feature_request.yml`。
- Issue 中避免上传敏感发票原件；如需复现，应先脱敏文件名、税号、金额、公司名称等信息。

## Actions 管理

当前仓库包含：

- `.github/workflows/ci.yml`：push 到 `main` 和 PR 时运行语法检查与单元测试。
- `.github/workflows/build-windows.yml`：手动触发 Windows 打包并上传 artifact。

维护规则：

- CI 应保持快速、稳定，不依赖本地绝对路径。
- 打包 workflow 只上传 artifact，不把生成的 zip 重新提交到仓库。
- 修改依赖或 Python 版本时，同步更新 README 和 workflow。

## Release 管理

- 发布包放在 GitHub Releases，不直接提交到仓库。
- Release 标题建议使用 `vX.Y.Z - 简短说明`。
- Release 描述建议包含：新增功能、修复内容、已知限制、校验方式、下载说明。
- macOS Apple Silicon、macOS Intel、Windows 包需要分别标明平台。

## 维护检查表

每次准备同步 GitHub 前检查：

- [ ] `git status -sb` 中没有无关文件。
- [ ] `.gitignore` 已覆盖本地输出、缓存和打包产物。
- [ ] `README.md` 与当前功能一致。
- [ ] `CHANGELOG.md` 记录了本次主要变化。
- [ ] 已运行编译检查和单元测试。
- [ ] PR 或 Release 描述包含验证方式。
