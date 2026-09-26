import tempfile
import unittest
from pathlib import Path
from face_capture.log_reader import LogTail


class LogReaderTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'test-output'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'capture.log'

    def test_new_lines_only_and_incomplete_utf8_is_preserved(self):
        self.path.write_bytes(b'first\n')
        tail = LogTail(self.path)
        self.assertEqual(tail.read_lines(), ['first'])
        self.assertEqual(tail.read_lines(), [])
        message = '采集成功\n'.encode()
        with self.path.open('ab') as stream: stream.write(message[:5])
        self.assertEqual(tail.read_lines(), [])
        with self.path.open('ab') as stream: stream.write(message[5:])
        self.assertEqual(tail.read_lines(), ['采集成功'])

    def test_missing_then_created_and_rotated_file(self):
        tail = LogTail(self.path)
        self.assertEqual(tail.read_lines(), [])
        self.path.write_text('old log\n', encoding='utf-8')
        self.assertEqual(tail.read_lines(), ['old log'])
        self.path.rename(self.path.with_suffix('.log.1'))
        self.path.write_text('new log after rotation\n', encoding='utf-8')
        self.assertEqual(tail.read_lines(), ['new log after rotation'])

    def test_initial_read_is_bounded_and_starts_at_complete_line(self):
        self.path.write_bytes(b'old\n' * 100 + b'last\n')
        tail = LogTail(self.path, max_bytes=20)
        lines = tail.read_lines()
        self.assertIn('last', lines)
        self.assertLessEqual(len(lines), 5)
        self.assertTrue(all(line in ('old', 'last') for line in lines))

    def test_truncation_starts_at_new_beginning(self):
        self.path.write_text('long old log line\n', encoding='utf-8')
        tail = LogTail(self.path)
        tail.read_lines()
        self.path.write_text('new\n', encoding='utf-8')
        self.assertEqual(tail.read_lines(), ['new'])
