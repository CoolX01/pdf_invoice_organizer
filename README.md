# PDF 发票自动整理归纳工具

一个基于 Python + Qt 的本地桌面工具，用于批量导入 PDF 发票、解析关键信息、在界面中预览结果，并导出 Excel。

这个仓库保留源码、配置、打包脚本和文档，不提交本地虚拟环境、构建目录、`.app`、`.exe`、压缩包等产物。

## 功能概览

- 批量导入 PDF 发票
- 支持拖拽 PDF 到窗口
- 优先直接提取 PDF 文本，必要时自动 OCR 兜底
- 在 GUI 中预览解析结果、总金额和重复组数
- 支持重复文件识别、重复发票号码标记
- 支持从结果中移除重复项
- 支持导出 `.xlsx`
- 预留模板导出能力

## 仓库结构

```text
pdf_invoice_organizer/
├── app/
│   ├── mac/
│   ├── mac_intel/
│   └── windows/
├── release/
│   └── mac/
│       ├── apple_silicon/
│       └── intel/
├── runtime/
│   └── README.md
├── source/
│   ├── app.py
│   ├── assets/
│   ├── config/
│   ├── exporters/
│   ├── models/
│   ├── parsers/
│   ├── services/
│   ├── ui/
│   └── utils/
├── tools/
│   ├── build_mac_intel.command
│   ├── build_windows.bat
│   ├── invoice_organizer.spec
│   ├── invoice_organizer_windows.spec
│   └── start_invoice_app.bat
├── build_mac_intel.command
├── build_windows.bat
├── main.py
├── start_invoice_app.bat
└── start_invoice_app.command
```

## 环境要求

- Python 3.9+
- macOS 或 Windows
- 推荐使用虚拟环境

核心依赖见 [source/requirements.txt](source/requirements.txt)。

## 本地开发启动

1. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. 安装依赖

```bash
pip install -r source/requirements.txt
```

3. 启动程序

```bash
python main.py
```

## 打包说明

### macOS Apple Silicon

在 Apple Silicon Mac 上执行：

```bash
python -m PyInstaller tools/invoice_organizer.spec --noconfirm --distpath app/mac --workpath build/mac
```

### macOS Intel

在 Intel Mac 上执行：

```bash
./build_mac_intel.command
```

会生成：

```text
app/mac_intel/PDF发票自动整理归纳工具.app
release/mac/intel/PDF发票自动整理归纳工具_mac_intel_YYYYMMDD_HHMMSS.zip
```

### Windows

在 Windows 环境中执行：

```text
build_windows.bat
```

会生成：

```text
app/windows/PDF发票自动整理归纳工具/
```

注意：Windows 当前是 `one-dir` 打包，发布时需要连同 `_internal` 目录一起分发，不能只发 `.exe`。

## 运行数据位置

项目目录内不保存用户运行数据。

macOS：
- 配置：`~/Library/Application Support/PDF发票自动整理归纳工具/`
- 日志：`~/Library/Logs/PDF发票自动整理归纳工具/`

Windows：
- 配置：`%APPDATA%\PDF发票自动整理归纳工具\`
- 日志：`%LOCALAPPDATA%\PDF发票自动整理归纳工具\logs\`

详细说明见 [runtime/README.md](runtime/README.md)。

## 主要入口

- 根入口：[main.py](main.py)
- 应用启动逻辑：[source/app.py](source/app.py)
- 主窗口：[source/ui/main_window.py](source/ui/main_window.py)
- 解析服务：[source/services/invoice_service.py](source/services/invoice_service.py)
- Excel 导出：[source/exporters/excel_exporter.py](source/exporters/excel_exporter.py)

## GitHub 发布建议

- 提交源码、文档、配置样例和打包脚本
- 不提交 `.venv`、`.venv_intel`、`.venv_windows`
- 不提交 `build/`、`.app`、`.exe`、压缩包、日志、`__pycache__`
- 用 GitHub Release 分发各平台打包产物，而不是直接放进仓库
