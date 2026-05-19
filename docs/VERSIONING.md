# 版本管理说明

本项目采用“稳定主线 + 功能分支 + GitHub Release”的轻量版本管理方式，确保源码、文档和发布包可追溯。

## 分支约定

- `main`：稳定主线，只合并已经通过测试和人工确认的版本。
- `codex/*`：功能开发、修复和自动化整理分支，例如 `codex/invoice-safety-ocr-tests`。
- `release/*`：如需在发布前冻结版本，可从 `main` 切出发布候选分支。
- `hotfix/*`：线上发布包出现紧急问题时使用，修复后合回 `main`。

## 版本号约定

使用语义化版本号：`vMAJOR.MINOR.PATCH`。

- `MAJOR`：不兼容的操作流程、数据结构或打包方式变化。
- `MINOR`：新增功能或明显增强，例如新增 OCR 复核、导出策略、界面模块。
- `PATCH`：缺陷修复、文档修正、兼容性补丁。
- 发布候选可使用 `vX.Y.Z-rc.1`、`vX.Y.Z-rc.2`。

当前应用内尚未固定独立版本号字段；正式发布时以 Git tag 和 GitHub Release 标题为准。

## 每次提交前检查

```bash
.venv/bin/python -m compileall main.py source tests
.venv/bin/python -m unittest discover -s tests
```

如果系统 Python 缺少依赖，应优先使用项目虚拟环境 `.venv`。不要把 `.venv`、构建目录、导出结果或压缩包提交到仓库。

## 发布流程

1. 确认工作区只包含本次版本相关文件：

   ```bash
   git status -sb
   git diff --stat
   ```

2. 更新文档：
   - `README.md`：面向 GitHub 首页的功能、启动和打包说明。
   - `CHANGELOG.md`：记录本次版本变化。
   - `docs/`：维护长期流程说明。

3. 运行测试并提交：

   ```bash
   git add README.md CHANGELOG.md docs .github source tests .gitignore
   git commit -m "Prepare invoice OCR review release"
   ```

4. 推送功能分支并创建 Pull Request：

   ```bash
   git push -u origin <branch>
   gh pr create --draft --fill
   ```

5. PR 通过 CI 和人工确认后合并到 `main`。

6. 正式发布时创建 tag 并推送：

   ```bash
   git checkout main
   git pull --ff-only
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin main --tags
   ```

7. 在 GitHub Releases 中创建对应 Release，并上传 macOS / Windows 打包产物。

## 不提交到 Git 的内容

- 本地虚拟环境：`.venv/`、`.venv_intel/`、`.venv_windows/`
- 构建产物：`build/`、`.app`、`.exe`、`_internal/`
- 发布压缩包：`release/**/*.zip`
- 本地运行输出：`output/`
- 缓存和系统文件：`__pycache__/`、`.DS_Store`、日志文件
