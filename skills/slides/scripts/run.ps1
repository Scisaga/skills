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

function Show-Usage {
  $RunCommand = "& '" + (Join-Path $ScriptDir 'run.ps1').Replace("'", "''") + "'"
  @"
Usage:
  $RunCommand bootstrap [--stage static|audio|narrated|video|all]
  $RunCommand doctor [--stage static|audio|narrated|video|all]
  $RunCommand inspect-input --document source.md --markdown-output input-preflight.md
  $RunCommand prepare-input-review --document source.md --output input-review.json
  $RunCommand validate-input --document source.md [--review input-review.json] --markdown-output input-gate.md
  $RunCommand refresh-input-gate --project C:\work\presentation [--input-profile auto|page-narration|narrative-plan|execution-plan|presentation-source] [--input-review input-review.json]
  $RunCommand init --output C:\work\presentation --name "Project" --deliverable narration_audio|static_html|animated_html|narrated_html --input-document source.md [--input-review input-review.json] [--page-script-source page-script.md] [--template-source template.css] [--seconds-per-page N] [--allow-substantial-rewrite]
  $RunCommand approve --project C:\work\presentation --stage content|visual|narration --approved-by NAME [--pages 3,7,10] [--allow-substantial-rewrite]
  $RunCommand prepare-narration --project C:\work\presentation [--chapter-max-seconds 240] [--performance-plan plan.json] [--force]
  $RunCommand manifest [--visual animation_manifest.json] --director narration_director.json --voice-profile voice_profile.json --output animation_manifest.json --review narration_review.md
  $RunCommand list-voices
  $RunCommand configure-voice --project C:\work\presentation [--provider auto|qwen3-tts-openai|azure-speech] [--qwen-voice VOICE_ID] [--voice azure-voice-name] [--rate +0%] [--pitch +0st]
  $RunCommand timing --manifest animation_manifest.json --output fast_animation_timing.json
  $RunCommand audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json
  $RunCommand voice-audition --project C:\work\presentation [--provider qwen3-tts-openai|azure-speech] [--voices voice-a,voice-b]
  $RunCommand synthesize --project C:\work\presentation
  $RunCommand replace-audio --project C:\work\presentation
  $RunCommand assemble-html --project C:\work\presentation
  $RunCommand export-video --project C:\work\presentation
  $RunCommand export-pages --project C:\work\presentation [--pages 8,9,14] --format pdf|png|jpg --output C:\work\selected.pdf
  $RunCommand migrate-html --project OLD --output NEW [--template-source theme.css]
  $RunCommand qa --project C:\work\presentation --level static|audio|standard
  $RunCommand rebuild --project C:\work\presentation --scope audio --qa standard
  $RunCommand validate --project C:\work\presentation [--stage content|visual|animation|narration|audio]
"@
}

if ($Command -in @("help", "-h", "--help")) {
  Show-Usage
  exit 0
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
  "approve" {
    & $Python (Join-Path $ScriptDir "approve_project.py") @CommandArgs
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
  "refresh-input-gate" {
    & $Python (Join-Path $ScriptDir "refresh_input_gate.py") @CommandArgs
  }
  "manifest" {
    & $Python (Join-Path $ScriptDir "build_manifest.py") @CommandArgs
  }
  "prepare-narration" {
    & $Python (Join-Path $ScriptDir "prepare_narration.py") @CommandArgs
  }
  "configure-voice" {
    & $Python (Join-Path $ScriptDir "audio_production.py") "configure-voice" @CommandArgs
  }
  "timing" {
    & $Python (Join-Path $ScriptDir "generate_fast_animation_timing.py") @CommandArgs
  }
  "audio-timeline" {
    & $Python (Join-Path $ScriptDir "build_audio_timeline.py") @CommandArgs
  }
  "synthesize" {
    & $Python (Join-Path $ScriptDir "audio_production.py") "synthesize" @CommandArgs
  }
  "voice-audition" {
    & $Python (Join-Path $ScriptDir "audio_production.py") "audition" @CommandArgs
  }
  "list-voices" {
    & $Python (Join-Path $ScriptDir "audio_production.py") "list-voices" @CommandArgs
  }
  "replace-audio" {
    & $Python (Join-Path $ScriptDir "html_production.py") "--replace-audio" @CommandArgs
  }
  "assemble-html" {
    & $Python (Join-Path $ScriptDir "html_production.py") @CommandArgs
  }
  "export-video" {
    & $Python (Join-Path $ScriptDir "html_export.py") "export-video" @CommandArgs
  }
  "export-pages" {
    & $Python (Join-Path $ScriptDir "html_export.py") "export-pages" @CommandArgs
  }
  "migrate-html" {
    & $Python (Join-Path $ScriptDir "migrate_html.py") @CommandArgs
  }
  "qa" {
    & $Python (Join-Path $ScriptDir "qa_presentation.py") @CommandArgs
  }
  "rebuild" {
    & $Python (Join-Path $ScriptDir "rebuild_presentation.py") @CommandArgs
  }
  "validate" {
    & $Python (Join-Path $ScriptDir "validate_project.py") @CommandArgs
  }
  { $_ -in @("help", "-h", "--help") } {
    Show-Usage
    exit 0
  }
  default {
    throw "Unknown command: $Command"
  }
}
exit $LASTEXITCODE
