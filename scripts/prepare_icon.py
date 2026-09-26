"""Stage the approved A artwork without replacing it during builds."""
from pathlib import Path
from shutil import copyfile

root = Path(__file__).resolve().parents[1]
assets = root / 'assets'
for extension in ('ico', 'png'):
    source = assets / 'icon-a' / f'face-capture.{extension}'
    target = assets / f'face-capture.{extension}'
    copyfile(source, target)
    print(target)
