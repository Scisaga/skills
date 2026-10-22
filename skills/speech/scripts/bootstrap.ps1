param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$PythonBin = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$env:PYTHONUTF8 = '1'
$CheckOnly = $false
$WithAzure = $false
$Mode = 'all'
$Provider = 'auto'
$DoctorArgs = @()
for ($i = 0; $i -lt $RemainingArgs.Count; $i++) {
  switch ($RemainingArgs[$i]) {
    '--check-only' { $CheckOnly = $true }
    '--with-azure' { $WithAzure = $true }
    '--mode' { $i++; if ($i -ge $RemainingArgs.Count) { throw '--mode needs a value' }; $Mode = $RemainingArgs[$i] }
    '--provider' { $i++; if ($i -ge $RemainingArgs.Count) { throw '--provider needs a value' }; $Provider = $RemainingArgs[$i] }
    default { $DoctorArgs += $RemainingArgs[$i] }
  }
}
if (-not $CheckOnly) {
  $VenvPath = Join-Path $SkillRoot '.venv-win'
  if (-not (Test-Path -LiteralPath (Join-Path $VenvPath 'Scripts/python.exe'))) {
    & $PythonBin -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  $PythonBin = Join-Path $VenvPath 'Scripts/python.exe'
  $Requirements = if ($WithAzure -or $Provider -eq 'azure-speech') { 'requirements-azure.txt' } else { 'requirements.txt' }
  & $PythonBin -m pip install -r (Join-Path $SkillRoot $Requirements)
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
  $LocalPython = Join-Path $SkillRoot '.venv-win/Scripts/python.exe'
  if (Test-Path -LiteralPath $LocalPython) { $PythonBin = $LocalPython }
}
& $PythonBin (Join-Path $ScriptDir 'doctor.py') --mode $Mode --provider $Provider @DoctorArgs
exit $LASTEXITCODE
