import unittest
from face_capture.actions import ActionTracker, Sample


class ActionTests(unittest.TestCase):
    def drive(self, tracker, start, duration, **values):
        result = None
        for i in range(round(duration / .05) + 1):
            result = tracker.update(Sample(**values), round(start + i * .05, 3))
        return result

    def test_blink_requires_open_closed_open_then_good_photo(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        r = self.drive(t, .75, .3)
        self.assertEqual(r['completedActions'], ['blink'])
        self.assertTrue(r['captureReady'])

    def test_final_return_frame_captures_without_second_hold(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        self.drive(t, .75, .15)
        r = t.update(Sample(), .95)
        self.assertEqual(r['completedActions'], ['blink'])
        self.assertTrue(r['captureReady'])

    def test_first_clear_frame_after_blur_captures_immediately(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        self.drive(t, .75, .3, sharpness=55)
        r = t.update(Sample(sharpness=65), 1.1)
        self.assertTrue(r['captureReady'])

    def test_unmet_photo_condition_has_specific_reason(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        self.drive(t, .75, .3, sharpness=5)
        r = t.update(Sample(sharpness=5), 1.1)
        self.assertEqual(r['captureBlockReason'], 'BLURRY')
        self.assertIn('模糊', r['prompt'])
        r = t.update(Sample(pitch=20), 1.15)
        self.assertEqual(r['captureBlockReason'], 'HEAD_POSE')
        self.assertIn('抬头', r['prompt'])

    def test_single_closed_frame_does_not_pass(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        t.update(Sample(blink=.9), .55)
        r = self.drive(t, .6, 1)
        self.assertEqual(r['completedActions'], [])

    def test_turn_requires_return_to_center(self):
        t = ActionTracker(['turn_left'], 0)
        self.drive(t, 0, .5)
        r = self.drive(t, .55, .6, yaw=25)
        self.assertEqual(r['completedActions'], [])
        r = self.drive(t, 1.2, .4)
        self.assertEqual(r['completedActions'], ['turn_left'])

    def test_mouth_requires_close_after_open(self):
        t = ActionTracker(['mouth'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .5, mouth=.8)
        r = self.drive(t, 1.1, .4)
        self.assertEqual(r['completedActions'], ['mouth'])

    def test_multiple_faces_reset_completed_actions(self):
        t = ActionTracker(['blink', 'turn_right'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        self.drive(t, .75, .3)
        r = t.update(Sample(faces=2), 1.1)
        self.assertEqual(r['completedActions'], [])
        self.assertFalse(r['captureReady'])

    def test_blurry_or_side_face_never_captured(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .5)
        self.drive(t, .55, .15, blink=.9)
        self.drive(t, .75, .3)
        r = self.drive(t, 1.1, 1, sharpness=5)
        self.assertFalse(r['captureReady'])
        r = self.drive(t, 2.2, 1, yaw=25)
        self.assertFalse(r['captureReady'])

    def test_deadline_cannot_be_extended_by_missing_face(self):
        t = ActionTracker(['blink'], 0, timeout=10)
        t.update(Sample(faces=0), 9)
        r = t.update(Sample(), 10.1)
        self.assertEqual(r['errorCode'], 'ACTION_TIMEOUT')

    def test_single_eye_closed_is_not_neutral(self):
        self.assertFalse(ActionTracker.neutral(Sample(blink=.01, eye_closed_max=.99)))

    def test_missing_face_then_delayed_recovery_resets_action(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .3)
        self.drive(t, .35, .15, blink=.9)
        t.update(Sample(faces=0), .5)
        r = self.drive(t, 1.2, .4)
        self.assertEqual(r['completedActions'], [])

    def test_long_frame_gap_cannot_complete_in_progress_action(self):
        t = ActionTracker(['blink'], 0)
        self.drive(t, 0, .3)
        self.drive(t, .35, .15, blink=.9)
        r = self.drive(t, 1.2, .4)
        self.assertEqual(r['completedActions'], [])


if __name__ == '__main__':
    unittest.main()
