param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")

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

function Pick-Python {
  $candidates = @(
    $env:PYTHON,
    (Join-Path $SkillRoot ".venv-win\Scripts\python.exe"),
    (Join-Path $SkillRoot ".venv\Scripts\python.exe"),
    (Join-Path $SkillRoot ".venv\bin\python"),
    "python",
    "python3"
  )

  foreach ($candidate in $candidates) {
    if (Test-PythonCommand $candidate) {
      return $candidate
    }
  }

  throw "Python is required. Run skills/subtitle-matcher/scripts/bootstrap.ps1 first."
}

function Show-Help {
  @"
Usage:
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 bootstrap
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 doctor
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 inventory --root "\\10.0.6.20\share\7 Download" --output inventory.json
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 normalize-existing --root "\\10.0.6.20\share\7 Download" --dry-run
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 normalize-existing --root "\\10.0.6.20\share\7 Download" --apply
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 validate-subtitle --video movie.mkv --subtitle movie.chs.srt
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 search-download --root "\\10.0.6.20\share\7 Download"
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 scan-report --root "\\10.0.6.20\share\7 Download"
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 register-vlc-protocol
  powershell -ExecutionPolicy Bypass -File .\skills\subtitle-matcher\scripts\run.ps1 audit-report --legacy-csv "\\10.0.6.20\share\7 Download\_subtitle_download_report.csv" --root "\\10.0.6.20\share\7 Download"
"@
}

$Command = "help"
$ArgsForCommand = @()

if ($RemainingArgs.Count -gt 0) {
  $Command = $RemainingArgs[0]
  if ($RemainingArgs.Count -gt 1) {
    $ArgsForCommand = $RemainingArgs[1..($RemainingArgs.Count - 1)]
  }
}

switch ($Command) {
  "bootstrap" {
    & (Join-Path $ScriptDir "bootstrap.ps1") @ArgsForCommand
  }
  { $_ -in @("doctor", "check") } {
    $PythonBin = Pick-Python
    & $PythonBin (Join-Path $ScriptDir "doctor.py") @ArgsForCommand
  }
  "search-download" {
    $PythonBin = Pick-Python
    & $PythonBin (Join-Path $ScriptDir "download_subtitles.py") @ArgsForCommand
  }
  "register-vlc-protocol" {
    & (Join-Path $ScriptDir "register-vlc-protocol.ps1") @ArgsForCommand
  }
  "unregister-vlc-protocol" {
    & (Join-Path $ScriptDir "register-vlc-protocol.ps1") -Unregister
  }
  { $_ -in @("inventory", "normalize-existing", "validate-subtitle", "scan-report", "audit-report") } {
    $PythonBin = Pick-Python
    & $PythonBin (Join-Path $ScriptDir "subtitle_matcher.py") $Command @ArgsForCommand
  }
  { $_ -in @("help", "-h", "--help") } {
    Show-Help
  }
  default {
    throw "Unknown command: $Command. Use run.ps1 help for usage."
  }
}
