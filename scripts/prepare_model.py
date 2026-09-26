"""Download the versioned official model and verify its pinned checksum."""
import hashlib
from pathlib import Path
import urllib.request

URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
target = Path(__file__).resolve().parents[1] / 'models/face_landmarker.task'
target.parent.mkdir(exist_ok=True)
if not target.exists():
    temporary = target.with_suffix('.download')
    urllib.request.urlretrieve(URL, temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
        temporary.unlink()
        raise SystemExit('Model checksum mismatch')
    temporary.replace(target)
if hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
    raise SystemExit('Existing model checksum mismatch')
print('Model verified:', target)
