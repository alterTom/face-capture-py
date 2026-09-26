<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps({
  baseUrl: { type: String, default: 'http://127.0.0.1:18765' },
  cameraIndex: { type: Number, default: 0 },
  actionPool: { type: Array, default: () => ['blink', 'mouth', 'turn_left', 'turn_right'] },
  // Bind to dialog visibility when the dialog keeps its content mounted.
  active: { type: Boolean, default: true },
  autoStart: { type: Boolean, default: true },
  mirror: { type: Boolean, default: true }
});
const emit = defineEmits(['success', 'error', 'status', 'cancel']);
const supported = new Set(['blink', 'mouth', 'turn_left', 'turn_right']);
const imageUrl = ref('');
const busy = ref(false);
const action = ref(null);
const connecting = ref(false);
const isPhoto = ref(false);
let current = null;
let disposed = false;

function clearImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value);
  imageUrl.value = '';
  isPhoto.value = false;
}

function showImage(blob, photo = false) {
  const url = URL.createObjectURL(blob);
  clearImage();
  imageUrl.value = url;
  isPhoto.value = photo;
}

function cancel() {
  const previous = current;
  current = null; // Invalidate callbacks before aborting the SDK.
  busy.value = false;
  action.value = null;
  clearImage();
  connecting.value = false;
  if (previous) {
    previous.client.cancel();
    if (!disposed) emit('cancel');
  }
}

async function start() {
  if (disposed || !props.active || current) return null;
  let round;
  try {
    const pool = [...new Set(props.actionPool)];
    if (!pool.length || pool.some(item => !supported.has(item))) {
      throw Object.assign(new Error('actionPool 必须包含至少一个受支持的动作'), { code: 'INVALID_ACTION_POOL' });
    }
    const Client = window.FaceCaptureClient;
    if (!Client) {
      throw Object.assign(new Error('浏览器采集 SDK 未加载，请检查组件包或页面脚本'), { code: 'SDK_NOT_LOADED' });
    }
    const selected = pool[Math.floor(Math.random() * pool.length)];
    round = { client: new Client(props.baseUrl), action: selected };
    current = round;
    clearImage();
    busy.value = true;
    connecting.value = true;
    action.value = selected;
    const blob = await round.client.capture({
      actions: [selected],
      cameraIndex: props.cameraIndex,
      requireConsent: false,
      onPreview: blob => {
        if (current !== round || disposed) return;
        showImage(blob);
        connecting.value = false;
      },
      onStatus: state => {
        if (current !== round || disposed) return;
        emit('status', state);
      }
    });
    if (disposed || current !== round) return null;
    showImage(blob, true);
    current = null;
    busy.value = false;
    connecting.value = false;
    const result = { blob, action: selected };
    emit('success', result);
    return result;
  } catch (error) {
    if (disposed || (round && current !== round)) return null;
    current = null;
    busy.value = false;
    clearImage();
    connecting.value = false;
    emit('error', error);
    return null;
  }
}

watch(() => props.active, active => {
  if (!active) cancel();
  else if (props.autoStart) void start();
}, { flush: 'sync' });
onMounted(() => {
  window.addEventListener('pagehide', cancel);
  if (props.active && props.autoStart) void start();
});
onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener('pagehide', cancel);
  cancel();
});

defineExpose({ start, cancel, busy: computed(() => busy.value),
  connecting: computed(() => connecting.value), action: computed(() => action.value) });
</script>

<template>
  <section v-if="active" class="face-capture" aria-label="人脸照片采集">
    <div class="face-capture__frame" :aria-busy="busy">
      <img
        v-if="imageUrl"
        class="face-capture__image"
        :class="{ 'face-capture__image--mirrored': mirror && !isPhoto }"
        :src="imageUrl"
        :alt="isPhoto ? '抓拍的人脸照片' : '摄像头实时取景'"
      >
      <div v-else class="face-capture__placeholder" aria-label="等待人脸采集">
        <svg viewBox="0 0 200 240" aria-hidden="true">
          <path d="M100 22c-40 0-48 24-40 61-15 0-12 34 3 38 4 22 15 35 23 44v18c0 15-31 18-66 41 40 27 120 27 160 0-35-23-66-26-66-41v-18c8-9 19-22 23-44 15-4 18-38 3-38 8-37 0-61-40-61Z" />
        </svg>
      </div>
      <div v-if="!isPhoto" class="face-capture__guide" aria-hidden="true" />
      <div class="face-capture__ring" :class="{ 'face-capture__ring--connecting': connecting }" aria-hidden="true" />
    </div>
  </section>
</template>

<style scoped>
.face-capture {
  box-sizing: border-box;
  width: 100%;
  color: #203251;
  text-align: center;
  background: #fff;
  font-family: inherit;
}
.face-capture__frame {
  position: relative;
  width: min(100%, 340px, 48vh);
  aspect-ratio: 1;
  margin: 0 auto;
  overflow: hidden;
  border-radius: 50%;
  background: #f3f5ff;
  box-sizing: border-box;
}
.face-capture__image { display: block; width: 100%; height: 100%; object-fit: cover; }
.face-capture__image--mirrored { transform: scaleX(-1); }
.face-capture__placeholder { display: grid; place-items: center; height: 100%; }
.face-capture__placeholder svg { width: 53%; height: 65%; fill: #dce3ff; stroke: #617af5; stroke-width: 4; }
.face-capture__guide {
  position: absolute;
  inset: 14% 25%;
  border: 1px dashed rgb(255 255 255 / 80%);
  border-radius: 48%;
  pointer-events: none;
}
.face-capture__ring {
  position: absolute;
  inset: 0;
  border: 5px solid #70e3e6;
  border-top-color: #526ef1;
  border-radius: 50%;
  pointer-events: none;
}
.face-capture__ring--connecting { animation: face-capture-spin 1.1s linear infinite; }
@keyframes face-capture-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .face-capture__ring--connecting { animation: none; border-style: dashed; }
}
</style>
