param([string]$IsccPath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Create .venv and install requirements-dev.txt first.' }
$env:MPLCONFIGDIR = Join-Path $projectRoot '.cache/matplotlib'
$env:FACE_CAPTURE_DATA_DIR = Join-Path $projectRoot 'test-output/build-runtime'
New-Item -ItemType Directory -Force $env:MPLCONFIGDIR | Out-Null
& $pythonExe scripts/prepare_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed.' }
& $pythonExe scripts/prepare_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon preparation failed.' }
& $pythonExe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& node tests/test_sdk.cjs
if ($LASTEXITCODE -ne 0) { throw 'Browser SDK tests failed.' }
& $pythonExe -m PyInstaller --noconfirm --clean packaging/FaceCapture.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$selfTest = Start-Process -FilePath "$projectRoot/dist/FaceCapture/FaceCapture.exe" -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru
if ($selfTest.ExitCode -ne 0) { throw 'Packaged model self-test failed. See test-output/build-runtime/logs.' }
if (-not $IsccPath) {
    $isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($isccCommand) { $IsccPath = $isccCommand.Source }
    else {
        $IsccPath = @('C:/Program Files (x86)/Inno Setup 6/ISCC.exe','C:/Program Files/Inno Setup 6/ISCC.exe','D:/appInstall/Inno Setup 6/ISCC.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
}
if (-not $IsccPath) { throw 'Inno Setup 6 not found. Pass -IsccPath <path to ISCC.exe>.' }
& $IsccPath packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
Get-FileHash dist/installer/*.exe -Algorithm SHA256 | Format-List
