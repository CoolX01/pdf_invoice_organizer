# PDF 发票自动整理归纳工具

一个本地运行的 Python + Qt 桌面工具，用于批量识别 PDF 发票、复核异常记录、去重并导出 Excel 汇总表。

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey)
![Release](https://img.shields.io/github/v/release/CoolX01/pdf_invoice_organizer)
![License](https://img.shields.io/badge/License-MIT-green)

## 下载

- 最新版本：[GitHub Releases](https://github.com/CoolX01/pdf_invoice_organizer/releases/latest)
- Windows 发布包：下载 Release 页面中的 `PDF-Invoice-Organizer-windows-*.zip`，解压后运行程序。
- macOS 用户可先按下方“源码运行”方式启动；如需打包，请参考仓库内打包脚本和平台说明。

## 适用场景

- 批量整理 PDF 发票，提取发票号码、金额、日期、购销方等字段。
- 本地处理发票文件，避免把敏感票据上传到第三方在线服务。
- 导出 Excel，用于报销、对账、归档或人工复核。

## 界面预览

![界面截图](source/assets/screenshot.png)

## 功能亮点

- 批量导入 PDF 文件或整个文件夹，支持拖拽添加。
- 自动校验 PDF 后缀、文件大小和文件头，跳过异常文件。
- 优先读取 PDF 文本层；字段缺失、版式错序或疑似串字段时自动 OCR 复核/补全。
- 在界面中查看识别状态、失败原因、需复核记录、重复文件和重复票号。
- 支持按“全部 / 失败 / 复核 / 重复”筛选结果，并用颜色提示风险行。
- 支持相同文件去重、相同发票号码标记，以及金额 / 日期 / 销售方冲突提示。
- 导出 `.xlsx`，自动生成“问题汇总”工作表，便于定位异常记录。
- 导出目标已存在时自动另存为带时间戳的新文件，避免覆盖旧结果。

## 安全边界

- 默认不会自动重命名、移动、删除或归档 PDF 原文件。
- “移到废纸篓/回收站”只针对检测到的重复本地文件，并会弹窗二次确认。
- 运行数据保存在系统用户目录；项目目录不保存用户发票数据。
- Issue 或截图中请先脱敏公司名、税号、金额、发票号码等敏感信息。

运行数据位置详见 [runtime/README.md](runtime/README.md)。

## 源码运行

环境要求：Python 3.9+，macOS 或 Windows。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r source/requirements.txt
python main.py
```

Windows PowerShell 可使用：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r source/requirements.txt
python main.py
```

## 测试

```bash
python -m compileall main.py source tests
python -m unittest discover -s tests
```

当前测试覆盖解析器、批处理去重、Excel 导出、配置读写、PDF 文件校验、文本提取 fallback 和自动 OCR 复核逻辑。

## 项目结构

```text
source/   应用源码、界面、解析、导出和工具模块
tests/    单元测试
.github/  CI、Issue 模板和 PR 模板
docs/     版本管理与 GitHub 维护说明
tools/    打包配置与辅助脚本
runtime/  运行期配置和日志位置说明
```

## 版本与维护

- 更新日志：[CHANGELOG.md](CHANGELOG.md)
- 版本管理规则：[docs/VERSIONING.md](docs/VERSIONING.md)
- GitHub 维护说明：[docs/GITHUB_MANAGEMENT.md](docs/GITHUB_MANAGEMENT.md)
- 正式发布包通过 [GitHub Releases](https://github.com/CoolX01/pdf_invoice_organizer/releases) 分发。

## 许可证

本项目使用 [MIT License](LICENSE)。
