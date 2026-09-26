from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files('mediapipe')
datas += [(str(root / 'models'), 'models'), (str(root / 'web'), 'web')]
datas += [(str(root / 'assets'), 'assets')]
datas += [(str(root / 'README.md'), '.'), (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
for distribution in ('mediapipe', 'opencv-contrib-python', 'numpy', 'fastapi', 'starlette',
                     'uvicorn', 'pydantic', 'pydantic-core', 'matplotlib', 'pillow', 'scipy',
                     'absl-py', 'attrs', 'flatbuffers', 'protobuf', 'sounddevice', 'sentencepiece',
                     'PySide6-Essentials', 'shiboken6'):
    datas += copy_metadata(distribution)
a = Analysis([str(root / 'launcher.py')], pathex=[str(root)],
             binaries=collect_dynamic_libs('mediapipe'), datas=datas,
             hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
                            'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
                            'uvicorn.protocols.websockets.auto',
                            'uvicorn.protocols.websockets.wsproto_impl', 'uvicorn.lifespan.on'],
             excludes=['jax', 'jaxlib', 'tensorflow', 'torch', 'IPython', 'pytest'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FaceCapture',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=True, icon=str(root / 'assets/face-capture.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FaceCapture')
