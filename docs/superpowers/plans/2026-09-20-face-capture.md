# Face Capture Implementation Plan

> 使用 executing-plans 在当前空工作目录直接实现；用户已明确要求执行，不重复索取方案批准。

**Goal:** 构建浏览器调用的后台人脸采集程序和 Windows 安装包。
**Architecture:** FastAPI 管理会话；摄像头隔离子进程使用 MediaPipe 并执行纯 Python 动作状态机；浏览器轮询 JPEG 预览和进度。独立授权页允许任意业务来源获得本次会话授权。
**Tech Stack:** Python 3.12, FastAPI, OpenCV, MediaPipe, vanilla JS, PyInstaller, Inno Setup.
**Spec:** docs/spec.md

## Global Constraints
- 仅 127.0.0.1:18765；Windows 10/11 x64；无本地采集窗口。
- 任意业务域名可调用，授权与随机令牌按会话管理。
- 摄像头单任务独占；JPEG 不写磁盘；超时清理。
- 安装自动创建桌面快捷方式。

## Review Focus
- 未授权读取预览或照片应拒绝；外站不能代用户批准。
- 多人、人脸消失和仅单帧动作不能误通过。
- 网页关闭、取消和摄像头错误释放资源。
- 没有 Python 或网络时安装后的模型推理能初始化。
- 重复启动和端口占用不得启动第二个采集进程。

## Tasks
- [x] 1. tests/test_actions.py → face_capture/actions.py：先测试完整动作闭环、噪声、多人重置、超时与抓拍稳定条件，再实现 ActionTracker.update(sample, now)。运行 python -m unittest discover -s tests。
- [x] 2. tests/test_service.py → face_capture/sessions.py, vision.py, api.py：测试 pending → running → passed 的真实会话管理、授权校验、令牌错误、取消、TTL 与任意 Origin；只替换摄像头硬件边界。实现 SessionManager + CameraWorker 和路由。
- [x] 3. web/index.html, web/authorize.html, web/capture-sdk.js：接入真实 API，实现实时预览、动作进度、开始/取消、图片预览下载；浏览器验证无摄像头错误路径。
- [x] 4. face_capture/__main__.py, packaging/FaceCapture.spec, packaging/installer.iss, scripts/build.ps1：单实例后台启动、日志、协议注册和桌面快捷方式；构建目录包及安装包；运行已打包程序健康检查与模型初始化自检。
- [x] 5. README.md：安装、集成示例、接口、安全与验证边界；独立复核并修复阻断问题，记录最终测试结果。

## Execution ledger
- 当前目录为空且无 git；直接创建项目，不进行 git 提交或 worktree 操作。
- 使用项目内 .tools、.cache 和 .venv，避免修改全局 Python。

- 最终验证：25 项测试通过；最终打包程序健康、单实例、摄像头子进程错误回传及停止通过；浏览器模拟成功/取消及跨来源授权回传通过。详见 docs/validation.md。
- Ruling: 摄像头隔离到子进程，解决驱动阻塞时取消无法释放的问题。
- Ruling: 当前目录无 git，不创建分支、不提交，不安装到用户系统；交付独立安装包供真实电脑测试。
