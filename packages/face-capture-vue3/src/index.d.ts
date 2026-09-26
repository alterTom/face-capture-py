import type { ComponentPublicInstance, DefineComponent } from 'vue';

export type CaptureAction = 'blink' | 'mouth' | 'turn_left' | 'turn_right';
export interface CaptureResult {
  blob: Blob;
  action: CaptureAction;
}
export interface FaceCaptureProps {
  baseUrl?: string;
  cameraIndex?: number;
  actionPool?: CaptureAction[];
  active?: boolean;
  autoStart?: boolean;
  mirror?: boolean;
}
export type FaceCaptureInstance = ComponentPublicInstance & {
  start(): Promise<CaptureResult | null>;
  cancel(): void;
  readonly busy: boolean;
  readonly connecting: boolean;
  readonly action: CaptureAction | null;
};

declare const FaceCapture: DefineComponent<FaceCaptureProps>;
export { FaceCapture };
export default FaceCapture;
