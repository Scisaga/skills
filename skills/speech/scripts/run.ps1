param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$env:PYTHONUTF8 = '1'
$PythonBin = $null
foreach ($candidate in @($env:PYTHON, (Join-Path $SkillRoot '.venv-win/Scripts/python.exe'), (Join-Path $SkillRoot '.venv/Scripts/python.exe'), 'python', 'python3')) {
  if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
  try { & $candidate --version *> $null; if ($LASTEXITCODE -eq 0) { $PythonBin = $candidate; break } } catch { }
}
if (-not $PythonBin) { throw 'Python 3 is required.' }
$Command = if ($RemainingArgs.Count -gt 0) { $RemainingArgs[0] } else { 'help' }
$CommandArgs = @()
if ($RemainingArgs.Count -gt 1) { $CommandArgs = @($RemainingArgs | Select-Object -Skip 1) }
if ($Command -eq 'bootstrap') {
  & (Join-Path $ScriptDir 'bootstrap.ps1') @CommandArgs
  exit $LASTEXITCODE
}
$Entries = @{ 'synthesize' = 'synthesize.py'; 'tts' = 'synthesize.py'; 'transcribe' = 'transcribe.py'; 'asr' = 'transcribe.py'; 'doctor' = 'doctor.py'; 'check' = 'doctor.py'; 'list-voices' = 'list_voices.py' }
if ($Command -in @('help', '--help', '-h')) {
  Write-Output 'run.ps1 synthesize|transcribe|list-voices|doctor|bootstrap [arguments...]'
  exit 0
}
if (-not $Entries.ContainsKey($Command)) { throw "Unknown command: $Command" }
& $PythonBin (Join-Path $ScriptDir $Entries[$Command]) @CommandArgs
exit $LASTEXITCODE
