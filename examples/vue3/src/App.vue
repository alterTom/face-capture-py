<script setup>
import { onBeforeUnmount, ref } from 'vue';
import FaceCapture from 'face-capture-vue3';

const dialog = ref(null);
const capture = ref(null);
const visible = ref(false);
const prompt = ref('正在连接摄像头…');
const remaining = ref(null);
const photoUrl = ref('');
const selectedAction = ref('');
const labels = { blink: '眨眼', mouth: '张嘴', turn_left: '左转头', turn_right: '右转头' };

function open() {
  prompt.value = '正在连接摄像头…';
  remaining.value = null;
  visible.value = true;
  dialog.value.showModal();
}
function close() {
  // Cancel immediately, including dialogs that keep their content mounted.
  capture.value?.cancel();
  visible.value = false;
  if (dialog.value.open) dialog.value.close();
}
function success({ blob, action }) {
  if (photoUrl.value) URL.revokeObjectURL(photoUrl.value);
  // Caller owns this URL. The component owns its separate display URL.
  photoUrl.value = URL.createObjectURL(blob);
  selectedAction.value = labels[action];
  close();
  // Upload here if needed: form.append('photo', blob, 'face.jpg').
}
function retake() {
  prompt.value = '正在连接摄像头…';
  remaining.value = null;
  void capture.value.start();
}
function status(state) {
  prompt.value = state.prompt;
  remaining.value = state.remainingSeconds;
}
function failure(error) { prompt.value = error.message; remaining.value = null; }
onBeforeUnmount(() => { if (photoUrl.value) URL.revokeObjectURL(photoUrl.value); });
</script>

<template>
  <main>
    <h1>Vue3 人脸采集</h1>
    <p>业务页面控制弹窗，组件选择动作，本地程序检测并返回照片。</p>
    <button @click="open">打开采集弹窗</button>
    <section v-if="photoUrl">
      <h2>调用方收到的照片</h2>
      <img class="result" :src="photoUrl" alt="采集结果">
      <p>本轮动作：{{ selectedAction }}</p>
      <a :href="photoUrl" download="face.jpg">下载照片</a>
    </section>
    <dialog ref="dialog" aria-label="人脸采集认证" @cancel.prevent="close" @close="close">
      <h2>请完成照片采集</h2>
      <FaceCapture
        ref="capture"
        :active="visible"
        @success="success"
        @status="status"
        @error="failure"
      />
      <p role="status" aria-live="polite">{{ prompt }}</p>
      <p class="remaining"><template v-if="remaining != null">采集剩余 {{ remaining }} 秒</template></p>
      <footer>
        <button type="button" :disabled="capture?.busy" @click="retake">重新拍照</button>
        <button type="button" @click="close">退出认证</button>
      </footer>
    </dialog>
  </main>
</template>

<style>
body { margin: 0; font-family: system-ui, sans-serif; color: #203247; background: #f4f7fa; }
main { max-width: 800px; margin: 60px auto; padding: 0 24px; }
h1 { font-size: 30px; } h2 { font-size: 20px; }
p { line-height: 1.6; }
button, a { font: inherit; }
button { cursor: pointer; border: 0; border-radius: 8px; padding: 10px 18px; background: #235ec1; color: white; }
button:disabled { opacity: .5; cursor: wait; }
button.secondary { background: #e8edf4; color: #203247; }
dialog { box-sizing: border-box; width: min(580px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); border: 1px solid #d6dded; border-radius: 14px; padding: 28px 24px; text-align: center; }
dialog h2 { margin: 0 0 22px; font-size: 25px; }
dialog p { overflow-wrap: anywhere; }
dialog .remaining { min-height: 24px; }
dialog::backdrop { background: rgb(15 30 50 / 50%); }
footer { display: flex; gap: 14px; justify-content: center; }
.result { display: block; max-width: 360px; width: 100%; border-radius: 12px; }
</style>
