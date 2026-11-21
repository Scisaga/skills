param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$BootstrapArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvDir = Join-Path $SkillRoot ".venv-win"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Stage = "all"
if ($BootstrapArgs.Count -eq 2 -and $BootstrapArgs[0] -eq "--stage") {
  $Stage = $BootstrapArgs[1]
}
elseif ($BootstrapArgs.Count -ne 0) {
  throw "Usage: bootstrap.ps1 [--stage static|audio|narrated|video|all]"
}
$Requirements = switch ($Stage) {
  "audio" { "requirements-audio.txt" }
  { $_ -in @("static", "video") } { "requirements-html.txt" }
  { $_ -in @("narrated", "all") } { "requirements.txt" }
  default { throw "Unsupported stage $Stage" }
}

function Invoke-Python([string]$Executable, [string[]]$Arguments) {
  & $Executable @Arguments
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$CreateVenv = -not (Test-Path -LiteralPath $VenvPython -PathType Leaf)
if (-not $CreateVenv) {
  & $VenvPython -m pip --version *> $null
  $CreateVenv = $LASTEXITCODE -ne 0
}
if ($CreateVenv) {
  Invoke-Python $Python @("-m", "venv", $VenvDir)
}
Invoke-Python $VenvPython @("-m", "pip", "install", "-r", (Join-Path $SkillRoot $Requirements))
if ($Stage -ne "audio") {
  Invoke-Python $VenvPython @("-m", "playwright", "install", "chromium")
  Invoke-Python $VenvPython @((Join-Path $ScriptDir "html_fonts.py"))
}
if ($Stage -in @("narrated", "video", "all")) {
  & (Join-Path $ScriptDir "install_ffmpeg.ps1")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Invoke-Python $VenvPython @((Join-Path $ScriptDir "doctor.py"), "--stage", $Stage)
