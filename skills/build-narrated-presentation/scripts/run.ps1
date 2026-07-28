param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")

function Pick-Python {
  $candidates = @(
    $env:PYTHON,
    (Join-Path $SkillRoot ".venv-win\Scripts\python.exe"),
    (Join-Path $SkillRoot ".venv\Scripts\python.exe"),
    "python",
    "python3"
  )
  foreach ($candidate in $candidates) {
    if ([string]::IsNullOrWhiteSpace($candidate)) {
      continue
    }
    try {
      & $candidate --version *> $null
      if ($LASTEXITCODE -eq 0) {
        return $candidate
      }
    }
    catch {
      continue
    }
  }
  throw "Python 3 is required."
}

$Command = if ($RemainingArgs.Count -gt 0) { $RemainingArgs[0] } else { "help" }
$CommandArgs = if ($RemainingArgs.Count -gt 1) {
  $RemainingArgs[1..($RemainingArgs.Count - 1)]
} else {
  @()
}

if ($Command -eq "bootstrap") {
  & (Join-Path $ScriptDir "bootstrap.ps1") @CommandArgs
  exit $LASTEXITCODE
}

$Python = Pick-Python
switch ($Command) {
  { $_ -in @("doctor", "check") } {
    & $Python (Join-Path $ScriptDir "doctor.py") @CommandArgs
  }
  "init" {
    & $Python (Join-Path $ScriptDir "init_project.py") @CommandArgs
  }
  "inspect-input" {
    & $Python (Join-Path $ScriptDir "validate_input_document.py") "inspect" @CommandArgs
  }
  "prepare-input-review" {
    & $Python (Join-Path $ScriptDir "validate_input_document.py") "template" @CommandArgs
  }
  "validate-input" {
    & $Python (Join-Path $ScriptDir "validate_input_document.py") "gate" @CommandArgs
  }
  "manifest" {
    & $Python (Join-Path $ScriptDir "build_manifest.py") @CommandArgs
  }
  "timing" {
    & $Python (Join-Path $ScriptDir "generate_fast_animation_timing.py") @CommandArgs
  }
  "audio-timeline" {
    & $Python (Join-Path $ScriptDir "build_audio_timeline.py") @CommandArgs
  }
  "validate" {
    & $Python (Join-Path $ScriptDir "validate_project.py") @CommandArgs
  }
  { $_ -in @("help", "-h", "--help") } {
    @"
Usage:
  scripts\run.ps1 bootstrap
  scripts\run.ps1 doctor
  scripts\run.ps1 inspect-input --document source.md --markdown-output input-preflight.md
  scripts\run.ps1 prepare-input-review --document source.md --output input-review.json
  scripts\run.ps1 validate-input --document source.md --review input-review.json --markdown-output input-gate.md
  scripts\run.ps1 init --output C:\work\presentation --name "Project" --input-document source.md --input-review input-review.json
  scripts\run.ps1 manifest --visual animation_manifest.json --director narration_director.json --output animation_manifest.json --review narration_review.md
  scripts\run.ps1 timing --manifest animation_manifest.json --output fast_animation_timing.json
  scripts\run.ps1 audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json
  scripts\run.ps1 validate --project C:\work\presentation
"@
    exit 0
  }
  default {
    throw "Unknown command: $Command"
  }
}
exit $LASTEXITCODE
