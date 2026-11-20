$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONPATH = "$PSScriptRoot\.deps"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LanRemote-Windows --paths .deps desktop\main.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
