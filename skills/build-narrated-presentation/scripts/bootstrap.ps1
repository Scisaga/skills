param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $SkillRoot ".venv-win"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

& $Python -m venv $VenvDir
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $SkillRoot "requirements.txt")
& $VenvPython (Join-Path $ScriptDir "doctor.py")
