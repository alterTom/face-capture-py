# 第一版验证记录

日期：2026-09-20。平台：当前 Windows 开发机，Python 3.12.13 x64。

## 已通过

- `python -m unittest discover -s tests`：25 项通过。覆盖动作闭环、单帧噪声、单眼闭合、丢脸/帧间隙重置、多人、质量门槛、令牌隔离、任意业务 Origin、授权隔离、任务独占、取消、心跳超时、结果 TTL、相机错误。
- 实际创建子进程模拟驱动永久阻塞，取消后终止子进程，允许下一任务；不是仅 mock terminate 调用。
- MediaPipe 官方模型实际离线加载，并处理空白图像；打包后的 `FaceCapture.exe --self-test` 同样通过。
- 最终 PyInstaller 目录程序与 Inno Setup 安装包完整构建成功；不是复用其他项目的发布输出。
- 最终 EXE 实际启动并提供健康接口；重复启动立即退出；实际创建打包后的摄像头子进程，使用编号 9 验证 `CAMERA_UNAVAILABLE` 回传；`--stop` 正常停止主服务。报告：`test-output/packaged-smoke.json`。
- EXE 的 Windows PE Subsystem=2，无控制台窗口。
- 浏览器真实操作：服务连接、摄像头不可用提示、按钮恢复、取消流程。
- 浏览器模拟成功采集：真实采集管线与 HTTP/SDK/UI，仅替换硬件图像及动作输入。页面收到 JPEG，图片 naturalWidth=640、naturalHeight=480、complete=true。
- 跨来源浏览器验证：业务页 18767 → 服务 18766 → 本地授权页 → 点击允许 → 业务页显示 JPEG；浏览器控制台无错误。图片带 `SIMULATED TEST FRAME`，不是人脸。
- 独立代码复核发现的单眼闭合、动作中断与阻塞驱动问题已修复并复核。

## 尚未完成的实机验收

- 尚未在另一台无 Python 的干净电脑执行安装/卸载，也未实际验证桌面快捷方式和登录自启动。安装脚本包含这些操作，且已成功编译，但不把编译成功视为真实安装验证。
- 未完成真人眨眼、张嘴、左右转头及抓拍质量验收；需要用户摄像头实测并根据光照/眼镜等调整阈值。
- 跨来源已在本地两个端口验证；远程 HTTPS 业务域名、Chrome/Edge 本地网络权限与企业策略仍需部署环境实测。
- 安装包未进行代码签名。

## 环境记录

Windows 沙箱内创建 multiprocessing 命名管道曾报 WinError 5；经工具批准，在沙箱外重跑完整测试与构建，全部通过。没有据此认定目标用户机器也会遇到此错误。

上游 protobuf 产生 Python 3.14 兼容性弃用提示，当前打包运行时固定为 Python 3.12。MediaPipe 输出 CPU delegate/feedback 提示，离线模型自检成功。错误分支测试的异常日志为故意注入的测试异常。
