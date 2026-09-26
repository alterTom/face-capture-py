"""Time-based action validation; independent of cameras and ML runtime."""
from dataclasses import dataclass


ACTION_LABELS = {'blink': '请眨眼', 'mouth': '请张嘴后闭嘴',
                 'turn_left': '请向左转头后回正', 'turn_right': '请向右转头后回正'}


@dataclass(frozen=True)
class Sample:
    faces: int = 1
    blink: float = 0.0
    eye_closed_max: float = 0.0
    mouth: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    sharpness: float = 150.0
    brightness: float = 120.0
    size: float = .4
    centered: bool = True


class ActionTracker:
    def __init__(self, actions, started, timeout=45):
        if not actions or any(a not in ACTION_LABELS for a in actions):
            raise ValueError('Unsupported or empty actions')
        self.actions = list(actions)
        self.deadline = started + timeout
        self.completed = []
        self.phase = 'neutral'
        self.since = None
        self.last_time = None
        self.missing_since = None

    def _hold(self, condition, now, seconds):
        if not condition:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        return now - self.since >= seconds - 1e-6

    def _reset(self):
        self.completed.clear()
        self.phase = 'neutral'
        self.since = None

    @staticmethod
    def neutral(s):
        return (abs(s.yaw) < 12 and abs(s.pitch) < 15 and abs(s.roll) < 15
                and max(s.blink, s.eye_closed_max) < .3 and s.mouth < .25)

    @staticmethod
    def photo_issue(s):
        if abs(s.yaw) >= 12:
            return 'HEAD_POSE', '动作已通过，请转回正脸'
        if abs(s.pitch) >= 15 or abs(s.roll) >= 15:
            return 'HEAD_POSE', '动作已通过，请平视摄像头，避免低头、抬头或歪头'
        if max(s.blink, s.eye_closed_max) >= .3:
            return 'EYES_CLOSED', '动作已通过，请睁开双眼'
        if s.mouth >= .25:
            return 'MOUTH_OPEN', '动作已通过，请自然闭嘴'
        if s.brightness < 45:
            return 'TOO_DARK', '动作已通过，光线过暗，请增加正面照明'
        if s.brightness > 220:
            return 'TOO_BRIGHT', '动作已通过，光线过强，请避免直射灯光'
        if s.sharpness < 60:
            return 'BLURRY', '动作已通过，画面模糊，请保持稳定并改善光线'
        return None, '动作已通过，正在抓拍'

    def _photo_result(self, s, result):
        reason, prompt = self.photo_issue(s)
        result.update(action=None, prompt=prompt, captureBlockReason=reason,
                      captureReady=reason is None)
        return result

    def update(self, s, now):
        result = {'completedActions': list(self.completed), 'action': None,
                  'prompt': '', 'captureReady': False, 'captureBlockReason': None,
                  'errorCode': None}
        if now >= self.deadline:
            result.update(prompt='动作检测超时，请重新采集', errorCode='ACTION_TIMEOUT')
            return result
        if self.last_time is not None and now - self.last_time > .4:
            self._reset()
        if self.missing_since is not None and now - self.missing_since > .5:
            self._reset()
        result['completedActions'] = list(self.completed)
        self.last_time = now
        if s.faces != 1:
            self.since = None
            if self.missing_since is None:
                self.missing_since = now
            if s.faces > 1 or now - self.missing_since > .5:
                self._reset()
            result.update(completedActions=list(self.completed),
                          prompt='画面中只能有一张人脸' if s.faces > 1 else '请将人脸放入画面')
            return result
        self.missing_since = None
        if s.size < .18 or s.size > .8 or not s.centered:
            self.since = None
            result['prompt'] = '请居中，并调整与摄像头的距离'
            return result
        if len(self.completed) == len(self.actions):
            return self._photo_result(s, result)
        action = self.actions[len(self.completed)]
        result.update(action=action, prompt=ACTION_LABELS[action])
        if self.phase == 'neutral':
            result['prompt'] = '请先正对摄像头，睁眼并闭嘴'
            if self._hold(self.neutral(s), now, .3):
                self.phase, self.since = 'action', None
        elif self.phase == 'action':
            condition = {'blink': s.blink >= .55, 'mouth': s.mouth >= .5,
                         'turn_left': s.yaw >= 18, 'turn_right': s.yaw <= -18}[action]
            if self._hold(condition, now, .08 if action == 'blink' else .25):
                self.phase, self.since = 'return', None
        else:
            result['prompt'] = '请恢复正脸，睁眼并闭嘴'
            if self._hold(self.neutral(s), now, .2):
                self.completed.append(action)
                self.phase, self.since = 'neutral', None
                result['completedActions'] = list(self.completed)
                # The final action already requires .2s of neutral return.
                # Reuse that verification instead of restarting a .6s hold.
                if len(self.completed) == len(self.actions):
                    return self._photo_result(s, result)
        return result
