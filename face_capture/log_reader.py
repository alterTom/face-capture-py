"""Bounded, read-only tailing of rotating UTF-8 logs."""
import codecs
from pathlib import Path


class LogTail:
    def __init__(self, path, max_bytes=65536):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.identity = None
        self.position = 0
        self.pending = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def read_lines(self):
        try:
            with self.path.open('rb') as stream:
                import os
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                initial = self.identity is None
                if initial or identity != self.identity or stat.st_size < self.position:
                    self.position = max(0, stat.st_size - self.max_bytes) if initial else 0
                    self.pending = ''
                    self.decoder.reset()
                self.identity = identity
                stream.seek(self.position)
                chunk = stream.read(self.max_bytes)
                if initial and self.position:
                    # Skip the leading partial line (and any split UTF-8 character).
                    head = chunk.find(b'\n')
                    chunk = chunk[head + 1:] if head >= 0 else b''
                self.position = stream.tell()
        except OSError:
            return []
        text = self.pending + self.decoder.decode(chunk)
        lines = text.split('\n')
        self.pending = lines.pop()
        # Bound an unterminated line too, e.g. a faulty dependency's verbose output.
        self.pending = self.pending[-self.max_bytes:]
        return [line.rstrip('\r') for line in lines]
