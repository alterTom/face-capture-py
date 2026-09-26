# 人脸采集第一版

用户已确认按会话中的方案直接执行。目标 Windows 10/11 x64，普通摄像头，Chrome/Edge。0.2.0 按新增需求加入桌面日志窗口和系统托盘；不创建本地摄像头预览或控制台窗口。

## 交付
- 本机 127.0.0.1:18765 HTTP 服务，浏览器预览、动作提示、JPEG 照片展示。
- 任意业务网站可接入，不使用域名白名单，不发送 cookies。会话随机令牌隔离数据。
- 外部网站开始采集前，通过本地浏览器授权页明确确认本次摄像头使用；授权页不允许跨域读取或嵌入。示例页在用户点击开始后直接授权。
- 默认随机眨眼及转头两个动作，可请求眨眼、张嘴、左右转头；连续帧验证、动作超时、单人检查、回正后选清晰帧。
- 一个活动会话；取消、断连心跳超时、任务超时后释放摄像头；照片只在内存短时保存。
- 摄像头与模型推理使用独立子进程，取消后若驱动阻塞则终止进程。
- 日志轮转，不记录照片或会话令牌。日志窗口实时显示采集过程、可打开测试页，关闭隐藏至托盘，右键退出。
- PyInstaller 目录包及 Inno Setup 安装包。安装自动创建当前用户桌面快捷方式、注册 facecapture 协议、登录自启动；安装完成显示日志窗口。重复双击快捷方式恢复已有窗口；登录自启动和协议唤起仅驻留托盘。
- 第一版为动作检测，不宣称可抵御视频回放、换人或深度伪造。

## 接口
GET /health；POST /capture/sessions；GET/DELETE /capture/sessions/{id}；GET /capture/sessions/{id}/preview；GET /capture/sessions/{id}/photo。
创建返回 sessionId、token、authorizeUrl；后续 HTTP 使用 Authorization: Bearer token。SDK 优先连接 /capture/sessions/{id}/stream，首条 JSON 消息携带会话令牌鉴权，通过 WebSocket 接收二进制 JPEG 预览和 JSON 状态；按批确认消息，未消费的旧预览不排队。任务状态附带 action、prompt、completedActions、errorCode。最终照片仍通过 HTTP 获取，类型 image/jpeg。WebSocket 不可用或断线时在同一会话回退 HTTP 轮询；原 HTTP 接口保留，SDK/Vue3 调用接口不变。

## 验证边界
自动化验证时序状态机、会话访问隔离、取消/超时、跨域与授权、模拟帧集成；真实摄像头、真人动作和不同机器安装效果必须如实区分，不用模拟测试冒充。
