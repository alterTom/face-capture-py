# Vue3 人脸取景组件

`FaceCapture.vue` 仅负责连接本机采集程序、显示实时预览/抓拍照片、回传结果。打开后自动随机选择一个动作并通过直接模式连接摄像头，不再打开本地二次授权页。

连接期间外圈旋转，收到第一帧后停止；结束、失败、取消也会停止。系统启用减少动态效果时改为静态虚线圈。只有圆圈旋转，人脸画面不旋转。

标题、动作提示、剩余时间、重新拍照/退出认证按钮以及弹窗关闭，全部由调用方控制。组件只发出 success，不关闭外层弹窗；示例调用方收到照片后关闭。

## 运行与升级

直接采集需要 0.2.1 或以上服务；当前仓库的安装包为 `dist/installer/FaceCapture-Setup-0.2.4-x64.exe`，也可以重启运行更新后的源码服务。仅更新 Vue 页面不能让旧采集程序支持直接采集。旧服务会报 DIRECT_CAPTURE_UNSUPPORTED，不会悄悄回退到弹出确认页。

本仓库内运行示例时，先构建本地包，再启动示例（Node.js 20.19+ 或 22.12+）：

```powershell
cd packages/face-capture-vue3
npm install
npm run build
cd ../../examples/vue3
npm ci
npm run dev
```

访问 http://127.0.0.1:5173/，打开弹窗即可开始。`npm test` 运行组件测试，`npm run build` 输出 dist/。

## 接入已有项目

发布 npm 包后，业务项目执行 `npm install face-capture-vue3`，然后直接导入组件。包内包含 SDK 和组件样式，无需另行复制或加载 `capture-sdk.js`。本仓库的示例使用本地 `file:` 依赖验证安装方式。

```vue
<script setup>
import { ref } from 'vue'
import FaceCapture from 'face-capture-vue3'

const visible = ref(false)
const captureRef = ref(null)
const prompt = ref('正在连接摄像头…')
const photo = ref(null)

function close() {
  captureRef.value?.cancel()
  visible.value = false
}
function success({ blob, action }) {
  photo.value = blob
  // 在这里交给业务系统：form.append('photo', blob, 'face.jpg')
  close() // 由调用方决定何时关闭
}
</script>

<template>
  <button @click="visible = true">打开采集</button>
  <YourDialog v-model="visible" @close="close">
    <h2>请完成照片采集</h2>
    <FaceCapture
      ref="captureRef"
      :active="visible"
      @status="prompt = $event.prompt"
      @error="prompt = $event.message"
      @success="success"
    />
    <p aria-live="polite">{{ prompt }}</p>
    <!-- 以下按钮完全属于调用方，可换成业务 UI 组件或其他布局 -->
    <button :disabled="captureRef?.busy" @click="captureRef.start()">重新拍照</button>
    <button @click="close">退出认证</button>
  </YourDialog>
</template>
```

YourDialog 表示业务系统自定义弹窗。完整原生 dialog 示例见 `src/App.vue`。不再使用旧版 `v-model:active`/`close` 事件，由调用方保存可见状态并处理 success。

## Props

| 属性 | 默认值 | 含义 |
| --- | --- | --- |
| active | true | true 显示，false 取消并清空图像；从 false 到 true 自动开始 |
| autoStart | true | 挂载/打开时自动开始；false 时由调用方执行 start() |
| baseUrl | http://127.0.0.1:18765 | 本机采集服务地址，下一轮生效 |
| cameraIndex | 0 | 摄像头编号 0–9，下一轮生效 |
| actionPool | ['blink', 'mouth', 'turn_left', 'turn_right'] | 每轮去重后随机一个动作，分别是眨眼、张嘴、左转头、右转头 |
| mirror | true | 实时预览镜像，抓拍 JPEG 保持原样 |

## 方法、状态和事件

- start(): 返回 Promise<{blob, action} | null>，失败通过 error 报告并返回 null，忙碌时重复调用返回 null。
- cancel(): 立即取消当前轮、清空画面并停止连接动画；不会直接关闭外层弹窗。
- busy: 当前是否有采集任务，用于调用方禁用重拍按钮。
- connecting: 是否正在等待首帧；服务 running 可能还在初始化摄像头，因此不会仅凭 running 提前停止动画。
- action: 最近选择的动作，每轮只发送 actions:[action]。
- success({blob, action}): 取得完整 image/jpeg 后触发一次。没有人脸身份或特征向量。未关闭时组件显示抓拍照片。
- status(state): 原样返回 prompt、status、remainingSeconds 等供调用方显示；passed 不能替代 success，因为照片可能还在下载。
- error(Error): 含 message 和可选 code，调用方负责提示、重试和是否关闭。
- cancel: 取消活动任务时触发；卸载时只清理，不回调业务。

关闭、卸载和 pagehide 会取消、释放预览 URL、忽略迟到回调。组件自己的 URL 与调用方接收到的 Blob 独立；调用方创建的 URL 自行释放。圆形预览只是显示裁剪，返回原始 JPEG。

## 服务协议与验证边界

组件调用 SDK 的 capture({requireConsent:false})，服务创建任务后直接启动摄像头。SDK 默认仍为 requireConsent:true，保持其他已有调用方式的行为。状态和照片读取继续需要会话令牌。

直接模式取消本地网页二次确认，不等于能替代操作系统摄像头权限或浏览器本地网络访问权限。当前服务允许所有 Origin，无来源白名单；可访问服务的网站也可申请直接采集，需按部署环境决定允许哪些网站访问本机服务。

同一时间仅一个任务。cancel 后后台异步释放摄像头，立即重试可能收到 CAMERA_BUSY，稍后重试。业务 CSP 需允许本机连接及 img-src blob:。

测试使用真实 Vue 挂载、真实 SDK 配合模拟 HTTP、可控 SDK 替身及 Python 模拟采集 worker。它们验证协议和生命周期，不代替真实摄像头动作检测验收。

实时预览和状态由 SDK 优先通过 WebSocket 接收，连接不可用时在同一会话内回退 HTTP。Vue3 组件的 props、事件和暴露方法保持不变；npm 包的 JavaScript 入口已包含 SDK 和样式。业务网页 CSP 需允许本地 HTTP 和 WebSocket 连接，后端程序须同步更新并重启。最终照片仍通过 HTTP 获取。
