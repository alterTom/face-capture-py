import os
import sys
from pathlib import Path


def resource_path(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return root / name


def data_dir():
    root = Path(os.environ.get('FACE_CAPTURE_DATA_DIR') or
                (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'FaceCapture'))
    root.mkdir(parents=True, exist_ok=True)
    return root
