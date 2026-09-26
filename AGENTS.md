# 仓库指南

## 项目结构与模块划分

`face_capture/` 包含 Python 服务、摄像头子进程、会话管理和 Windows 桌面界面。`web/` 存放浏览器 SDK 和本地页面。可分发的 Vue 3 组件包位于 `packages/face-capture-vue3/`，接入示例位于 `examples/vue3/`。Python 和 SDK 测试放在 `tests/`，Vue 组件测试放在 `examples/vue3/tests/`。构建脚本和打包配置分别位于 `scripts/`、`packaging/`；图标在 `assets/`，设计与验证记录在 `docs/`。

## 构建、测试与本地开发

在 Windows 上使用 Python 3.12 x64。先运行 `py -3.12 -m venv .venv`，再运行 `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`。启动服务前，运行 `.venv/Scripts/python.exe scripts/prepare_model.py` 下载并校验模型；随后运行 `.venv/Scripts/python.exe -m face_capture`。`models/*.task` 已被 Git 忽略。

运行 `.venv/Scripts/python.exe -m unittest discover -s tests` 执行 Python 测试，运行 `node tests/test_sdk.cjs` 执行浏览器 SDK 测试。使用 `npm --prefix examples/vue3 test` 和 `npm --prefix examples/vue3 run build` 测试、构建 Vue 示例。`./scripts/build.ps1 -IsccPath '<ISCC.exe的路径>'` 会执行检查并构建 Windows 程序及安装包，需要预先安装 Inno Setup 6。

## 代码风格与命名

遵循现有格式：Python 使用 4 个空格缩进，JavaScript 和 Vue 文件使用 2 个空格。Python 模块和函数使用 `snake_case`，JavaScript 变量使用 `camelCase`，Vue 组件文件使用 `PascalCase.vue`。修改通信协议时，同步检查服务端、SDK、Vue 组件包和示例。仓库尚未配置统一的格式化或代码检查工具；保持改动聚焦，并运行 `git diff --check`。

## 测试要求

Python 测试使用 `unittest`，文件命名为 `test_*.py`；JavaScript 测试使用 Node.js 内置测试运行器。修改会话、摄像头、SDK 或组件行为时，补充对应的回归测试。分别报告自动化测试结果，以及真实摄像头、目标浏览器和安装后环境的验证结果。

## 提交与拉取请求

目前历史中只有一次初始提交，尚无固定的提交消息规范。提交标题应简短，并直接描述所做的修改。拉取请求应说明行为变化、列出已运行的命令；有相关 Issue 时附上链接，涉及可见界面变化时附上截图。明确列出尚未完成的设备或安装验证。
