# face-capture-vue3

Vue3 人脸采集组件。包内包含浏览器 SDK；业务页面只需导入组件，不需要另行加载 `capture-sdk.js`。

组件负责连接本机 Face Capture 服务、显示预览和抓拍照片，并将 `{ blob, action }` 返回给调用方。弹窗、标题、按钮、业务提示和照片上传由调用方负责。

## 安装

发布到 npm 后：

```sh
npm install face-capture-vue3
```

使用者的 Windows 电脑还需安装并启动 Face Capture 桌面服务，版本至少为 0.2.1。仅安装 npm 包不能连接摄像头。默认服务地址是 `http://127.0.0.1:18765`。

## 使用

```vue
<script setup>
import { ref } from 'vue'
import FaceCapture from 'face-capture-vue3'

const visible = ref(false)
const capture = ref(null)
const message = ref('')

function close() {
  capture.value?.cancel()
  visible.value = false
}
function success({ blob, action }) {
  const form = new FormData()
  form.append('photo', blob, 'face.jpg')
  // 在此由业务系统上传 form，并按需要使用 action。
  close()
}
</script>

<template>
  <button @click="visible = true">开始采集</button>
  <YourDialog v-model="visible" @close="close">
    <FaceCapture
      ref="capture"
      :active="visible"
      @success="success"
      @status="message = $event.prompt"
      @error="message = $event.message"
    />
    <p>{{ message }}</p>
    <button :disabled="capture?.busy" @click="capture.start()">重新拍照</button>
    <button @click="close">退出认证</button>
  </YourDialog>
</template>
```

组件样式会随 JavaScript 入口自动加载，无需单独导入 CSS。需要手动管理样式时也可使用 `face-capture-vue3/style.css`。完整 Props、事件和方法说明见仓库的 `examples/vue3/README.md`。

组件默认使用免二次确认模式；旧版服务若不支持，会发出 `DIRECT_CAPTURE_UNSUPPORTED` 错误，不会切换到授权页。浏览器仍可能要求本地网络访问权限。业务网站的 CSP 须允许连接本机服务的 HTTP/WebSocket 地址，以及 `img-src blob:`。

发布到公开 npm 前，应先确定第三方使用许可，并审核本地服务的来源访问策略；当前服务允许所有 Origin。

## 仓库内构建

在此包目录运行 `npm install` 和 `npm run build`。构建后的 `dist/` 是 npm 发布内容；`npm pack --dry-run` 可查看文件清单。`examples/vue3` 通过本地 `file:` 依赖使用该包。
