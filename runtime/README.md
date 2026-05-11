# 运行数据说明

这个目录只用于说明运行数据的位置，实际运行数据不写回项目目录。

## macOS

- 用户配置：
  `~/Library/Application Support/PDF发票自动整理归纳工具/`
- 运行日志：
  `~/Library/Logs/PDF发票自动整理归纳工具/`

## Windows

- 用户配置：
  `%APPDATA%\PDF发票自动整理归纳工具\`
- 运行日志：
  `%LOCALAPPDATA%\PDF发票自动整理归纳工具\logs\`

## 设计目的

- 防止 `.app`、源码目录和运行数据混在一起
- 避免把运行日志、临时设置误打进发布包
- 让项目目录更接近正式交付结构
