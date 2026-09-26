# 人脸采集服务 · 第一版

Windows 10/11 x64 采集程序。浏览器显示摄像头预览、动作提示和自动抓拍照片；本地日志窗口和系统托盘用于查看运行过程、打开测试页及退出服务，不上传照片到任何第三方。

## 安装与使用

1. 运行 `dist/installer/FaceCapture-Setup-0.2.5-x64.exe`。
2. 安装器自动创建当前用户桌面的“人脸采集服务”快捷方式、开始菜单入口、登录自启动和 `facecapture://start` 协议，并启动后台服务。
3. 安装后显示日志窗口，窗口和任务栏有程序图标，系统托盘也有程序图标。点击窗口中的“打开测试页”，或访问 **http://127.0.0.1:18765/**。
4. 选择摄像头及动作，点击开始。按提示完成动作后保持正脸，照片直接显示在右侧，可下载 JPEG。
5. 点击窗口关闭按钮只隐藏到托盘，采集服务继续运行；单击托盘图标或再次双击桌面快捷方式可恢复日志窗口。托盘右键选择“退出程序”才会停止服务并释放摄像头。开始菜单“停止采集服务”仍可使用。

登录自启动时仅驻留托盘，不弹日志窗口；默认双击快捷方式则显示窗口。托盘隐藏后任务栏不再显示窗口按钮，这是 Windows 的常规行为。托盘图标可能被 Windows 放进折叠区域，可点击任务栏右下角的上箭头查看。无系统托盘时关闭窗口回退为任务栏最小化。

只为当前 Windows 用户安装；无需管理员权限、Python 或运行时联网。默认摄像头编号为 0；无法打开时尝试其他编号，并检查 Windows 设置 → 隐私和安全性 → 摄像头 → 允许桌面应用访问摄像头。安装包尚未代码签名。

## 业务网页接入

Vue3 项目可通过待发布的 [`face-capture-vue3` 包](packages/face-capture-vue3/README.md)使用 [`FaceCapture.vue`](examples/vue3/src/components/FaceCapture.vue)：打开自动随机单动作采集，不弹出二次确认，连接期间外圈旋转，成功回传 JPEG。包内包含浏览器 SDK 和样式。组件只负责连接与图像显示；标题、提示、重新拍照/退出按钮和弹窗关闭均由调用方控制。需配套 0.2.1 或以上采集程序。完整示例见 [Vue3 接入文档](examples/vue3/README.md)。

将 `web/capture-sdk.js` 复制到业务网站自身的静态目录。不要从 HTTP 本机地址加载业务 HTTPS 页的脚本。通过用户点击事件调用 `capture()`，浏览器会打开本地单次授权页，允许后回到业务网页完成采集。

```html
<button id="start">采集人脸</button>
<button id="cancel">取消</button>
<p id="progress"></p>
<img id="preview" alt="预览" style="max-width:480px;transform:scaleX(-1)">
<img id="photo" alt="抓拍结果" style="max-width:480px">
<script src="/static/capture-sdk.js"></script>
<script>
const client = new FaceCaptureClient('http://127.0.0.1:18765');
let previewUrl, photoUrl;
document.querySelector('#start').onclick = async () => {
  try {
    const blob = await client.capture({
      actions: ['blink', 'turn_left'], // 可省略，默认眨眼 + 随机左右转头
      cameraIndex: 0,
      onStatus: s => document.querySelector('#progress').textContent = s.prompt,
      onPreview: blob => {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(blob);
        document.querySelector('#preview').src = previewUrl;
      }
    });
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(blob);
    document.querySelector('#photo').src = photoUrl;
    // 需要上传时，由业务系统自行处理：
    // const form = new FormData();
    // form.append('photo', blob, 'face.jpg');
    // await fetch('/your-upload-endpoint', {method:'POST', body:form});
  } catch (error) {
    document.querySelector('#progress').textContent = error.message;
  }
};
document.querySelector('#cancel').onclick = () => client.cancel();
window.addEventListener('pagehide', () => client.cancel());
</script>
```

完整示例：`examples/integration.html`。可用 `.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1` 从项目根目录托管，然后访问 `http://127.0.0.1:8080/examples/integration.html` 测试不同来源接入。

所有业务域名都可接入，无业务域名白名单。HTTP 接口允许任意 Origin，禁用 cookie 凭证；状态、预览和照片必须附带随机会话 Bearer 令牌。默认 requireConsent=true 时创建任务等待本地确认；设置 requireConsent=false 直接启动摄像头，Vue3 组件使用此模式。直接模式取消了网页单次确认这一访问边界：可访问本机服务的网页也能申请直接采集，会话令牌只保护各任务的后续读取。授权页接口仍只允许同源调用，不用于直接模式。

业务网页应使用 HTTPS。浏览器可能要求“本地网络访问”授权，网页 CSP 的 `connect-src` 也须允许 `http://127.0.0.1:18765`。混合内容、弹出窗口及企业浏览器策略需要在目标 Chrome/Edge 版本验证；不要求用户关闭浏览器安全机制。无法唤起时，提示用户双击桌面快捷方式。

## HTTP 接口

服务固定监听 `127.0.0.1:18765`，不监听局域网地址。`/health` 返回的是服务及模型文件存在性；不代表已打开摄像头。

| 请求 | 用途 |
|---|---|
| GET /health | 服务名称、版本、模型文件就绪情况 |
| POST /capture/sessions | 创建任务，JSON 可含 actions、cameraIndex、requireConsent（默认 true，false 直接采集） |
| GET /capture/sessions/{id} | 状态与进度，同时更新浏览器心跳 |
| GET /capture/sessions/{id}/preview | 最新 JPEG 预览；未就绪返回 409 |
| GET /capture/sessions/{id}/photo | 成功后的 JPEG 照片；未就绪返回 409 |
| DELETE /capture/sessions/{id} | 取消任务并清理图像 |

创建响应含 `sessionId`、`token`、`status`、`authorizeUrl`（直接模式为 null，否则为授权页相对路径）。后续三个 GET 和 DELETE 必须发送 `Authorization: Bearer <token>`。授权页接口 `/consent/{id}` 供本地页面内部使用，业务网站不要直接调用。SDK 的 capture({requireConsent:false}) 使用直接模式。

状态：`pending_consent` → `running` → `passed` / `failed` / `cancelled` / `expired`，直接模式创建后立即进入 running。动作支持 `blink`、`mouth`、`turn_left`、`turn_right`，一次 1–4 个。错误返回 `errorCode` 和 `message`；任务失败原因在状态的 `errorCode`、`prompt` 中。

等待授权最多 60 秒，活动任务最多 60 秒，检测阶段最多 45 秒。运行时通过 WebSocket 消息确认维持心跳，回退 HTTP 时通过状态轮询维持心跳；15 秒没有心跳会中止任务。终态结果保留最多 120 秒；SDK 获取照片后会立即 DELETE 清理服务端图像。浏览器自己的 Blob 和下载文件由业务页面/用户管理。

## 日志和诊断

每次程序真正启动时，会清理上次运行的服务、采集和底层日志（含轮转备份），仅保留本次运行的日志。隐藏到托盘、再次打开窗口或采集子进程重启不会清空日志。下述轮转备份仅用于本次运行。

- `%LOCALAPPDATA%\FaceCapture\logs\capture.log`：任务生命周期、动作提示、错误和运行信息；2 MB 轮转，保留 5 份。
- `%LOCALAPPDATA%\FaceCapture\logs\camera.log`：摄像头子进程日志，按 2 MB 轮转。
- 摄像头生命周期使用中文日志，包含编号和任务 ID：正在连接、连接成功、连接失败、正在断开、已断开且资源已释放。失败的未连接句柄单独记录清理，不误报连接成功或正常断开。
- 强制结束时，服务日志记录请求停止、强制终止、进程已退出及退出码；这表示进程退出，不冒充执行了正常 camera.release()。日志窗口同时显示服务和采集两类记录。
- 同目录的 `capture-native.log`、`camera-native.log`：底层输出，启动时超过 2 MB 转为 previous 文件。
- 不记录照片内容或会话令牌；照片只在内存保存，不写文件。
- `FaceCapture.exe --self-test`：离线初始化模型并处理空白图像，写 `%LOCALAPPDATA%\FaceCapture\self-test.json`；不打开摄像头。
- `FaceCapture.exe --stop`：停止后台服务。
- `FaceCapture.exe --minimized`：启动后仅驻留系统托盘。
- 窗口实时显示 capture.log 和 camera.log 的新增行；最多保留 5000 行，不读取/显示照片内容。日志轮转后自动继续读取新文件。
- 数据目录可用 `FACE_CAPTURE_DATA_DIR` 环境变量覆盖，适用于隔离测试。

## 从源码开发和打包

```powershell
# 使用 Python 3.12 x64 创建环境
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe scripts/prepare_model.py
.venv/Scripts/python.exe -m face_capture

# 运行全部测试
.venv/Scripts/python.exe -m unittest discover -s tests
node tests/test_sdk.cjs

# 安装 Inno Setup 6 后生成目录程序和安装包
./scripts/build.ps1 -IsccPath 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe'
```

模型是 Google MediaPipe Face Landmarker float16 v1，由 `prepare_model.py` 从官方存储下载并校验固定 SHA256。构建时模型和网页一同打包，安装后不下载模型。依赖与模型的上游许可见 `THIRD_PARTY_NOTICES.md`。

## 第一版的能力边界

这是动作辅助拍照，不是高安全等级活体或身份核验。未实现照片/视频回放攻击、虚拟摄像头、深度伪造防御，也不校验采集者身份。多人或长时间丢失人脸会重置动作，但不能据此宣称防换人。

动作阈值为初始值，需要结合真实摄像头、光照、眼镜及使用人群校准。仅用普通 RGB 摄像头。摄像头和推理在独立后台子进程运行；取消或超时先请求正常释放，驱动阻塞时终止子进程，避免一个任务长期占用服务。

开发验证与实际验收记录见 `docs/validation.md`。

## 0.1.1 抓拍响应修复

- 最后一个动作完成已有的 0.2 秒回正验证后，当前帧符合质量条件即抓拍；取消再次连续等待 0.6 秒的重复验证，清晰度/姿态/光照/睁眼阈值不降低。
- 不达标时直接提示模糊、光线、头部角度、睁眼或闭嘴原因，并在 camera.log 中限频记录质量数值。
- 预览下载与完成状态轮询分离；JPEG 返回不再等待后台 DELETE 清理完成。
- 业务网站若自行部署过 `capture-sdk.js`，升级时也要替换为本版本文件。
- 构建环境还需要 Node.js 来运行 SDK 回归测试；最终用户电脑不需要 Node.js。

## 0.2.0 日志窗口与托盘

- 统一程序图标用于安装包、桌面快捷方式、任务栏、窗口及系统托盘。
- 日志窗口提供“打开测试页”和“打开日志文件夹”按钮；关闭窗口不会停止采集。
- 托盘单击恢复窗口，右键菜单包含显示窗口、打开测试页、退出程序。
- HTTP 服务在工作线程运行，摄像头仍使用隔离子进程；退出程序会停止服务并清理当前采集任务。
- 使用 PySide6-Essentials/QtWidgets，运行环境随安装包分发；目标电脑无需安装 Python 或 Qt。

## WebSocket 实时预览

新版 SDK 优先连接 `ws://127.0.0.1:18765/capture/sessions/{id}/stream`，以二进制 JPEG 推送预览，以 JSON 推送状态。创建、授权、取消和最终照片仍使用 HTTP；`capture`、`onPreview(blob)`、`onStatus(state)`、`cancel()` 调用方式不变，Vue3 组件无需改接口。业务端需更新或重新打包 `web/capture-sdk.js`，本机程序也需更新并重启。

- 连接后 5 秒内发送 `{"type":"auth","token":"会话令牌"}`，令牌不放在 URL 中，鉴权前不发送照片和状态。
- 状态消息为 `{"type":"status","state":{...}}`，state 与 HTTP 状态接口一致；错误消息为 `{"type":"error","errorCode":"...","message":"..."}`。
- 每批状态/预览后收到 `{"type":"sync"}`，客户端回复 `{"type":"ack"}`。服务端最多保留一批未确认消息，下一批读取最新照片；发送或确认超过 5 秒超时关闭连接。
- 预览维持最高约 10 帧/秒，确认消息维持会话心跳，无须同时轮询 HTTP。终态推送后关闭连接，成功照片通过 `/photo` 获取；取消和组件卸载由 SDK 关闭连接并 DELETE 清理。
- 无 WebSocket 支持、连接失败、断开或超过 8 秒未收到消息时，SDK 在同一会话内回退 HTTP 轮询，不重新启动摄像头；鉴权失败和任务失败直接报错。当前版本不自动重连 WebSocket。

业务网页 CSP 的 `connect-src` 需同时允许 `http://127.0.0.1:18765` 和 `ws://127.0.0.1:18765`。HTTPS、本地网络访问及企业策略仍需在目标浏览器验证；改成 WebSocket 不会绕过这些限制。后端运行依赖新增 `wsproto==1.2.0`，已加入依赖清单及打包配置。
