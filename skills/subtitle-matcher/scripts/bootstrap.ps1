param(
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $SkillRoot ".venv-win"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Test-PythonCommand {
  param([string]$Candidate)

  if ([string]::IsNullOrWhiteSpace($Candidate)) {
    return $false
  }

  try {
    & $Candidate --version *> $null
    return ($LASTEXITCODE -eq 0)
  }
  catch {
    return $false
  }
}

function Pick-HostPython {
  $candidates = @($env:PYTHON, "python", "python3")
  foreach ($candidate in $candidates) {
    if (Test-PythonCommand $candidate) {
      return $candidate
    }
  }

  throw "Python 3.10+ is required. Install Python or set the PYTHON environment variable."
}

if (Test-Path -LiteralPath $VenvPython) {
  $PythonBin = $VenvPython
}
elseif ($CheckOnly) {
  $PythonBin = Pick-HostPython
}
else {
  $HostPython = Pick-HostPython
  Write-Host "==> Creating subtitle-matcher Windows virtual environment"
  & $HostPython -m venv $VenvDir
  $PythonBin = $VenvPython
}

if (-not $CheckOnly) {
  Write-Host "==> Installing subtitle-matcher Python dependencies"
  & $PythonBin -m pip install -r (Join-Path $SkillRoot "requirements.txt")
}

Write-Host "==> Checking subtitle-matcher runtime"
& $PythonBin (Join-Path $ScriptDir "doctor.py")
