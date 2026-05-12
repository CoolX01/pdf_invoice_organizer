# 发布目录

这个目录用于说明各平台的发布方式，不提交实际二进制产物。

## 发布原则

- 源码、配置样例、打包脚本保留在仓库中
- `.app`、`.exe`、`.zip` 通过 GitHub Release 分发
- 运行日志和用户配置不进入仓库

## 平台说明

- [macOS 发布说明](mac/README.md)
- [Apple Silicon 发布说明](mac/apple_silicon/README.md)
- [Intel 发布说明](mac/intel/README.md)

## 推荐流程

1. 本地打包各平台产物
2. 在 GitHub Release 上传对应压缩包
3. 在 Release 文案里写清楚架构、版本号和日期
4. 保留仓库中的说明文档，便于以后复现打包过程

## 文件命名

- macOS Apple Silicon: `PDF发票自动整理归纳工具_mac_apple_silicon_YYYYMMDD_HHMMSS.zip`
- macOS Intel: `PDF发票自动整理归纳工具_mac_intel_YYYYMMDD_HHMMSS.zip`
- Windows: `PDF发票自动整理归纳工具_windows_YYYYMMDD_HHMMSS.zip`
