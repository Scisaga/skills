#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

pick_python() {
  local candidates=(
    "${PYTHON:-}"
    "${SKILL_ROOT}/.venv/bin/python"
    "${SKILL_ROOT}/.venv/Scripts/python.exe"
    "python3"
    "python"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [ -n "${candidate}" ] && command -v "${candidate}" >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
    if [ -n "${candidate}" ] && [ -f "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

COMMAND="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

if [ "${COMMAND}" = "bootstrap" ]; then
  exec "${SCRIPT_DIR}/bootstrap.sh" "$@"
fi
if ! PYTHON_BIN="$(pick_python)"; then
  echo "Error: Python 3 is required." >&2
  exit 1
fi

case "${COMMAND}" in
  doctor|check)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/doctor.py" "$@"
    ;;
  init)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/init_project.py" "$@"
    ;;
  approve)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/approve_project.py" "$@"
    ;;
  inspect-input)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/validate_input_document.py" inspect "$@"
    ;;
  prepare-input-review)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/validate_input_document.py" template "$@"
    ;;
  validate-input)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/validate_input_document.py" gate "$@"
    ;;
  refresh-input-gate)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/refresh_input_gate.py" "$@"
    ;;
  manifest)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/build_manifest.py" "$@"
    ;;
  prepare-narration)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/prepare_narration.py" "$@"
    ;;
  configure-voice)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/audio_production.py" configure-voice "$@"
    ;;
  timing)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/generate_fast_animation_timing.py" "$@"
    ;;
  audio-timeline)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/build_audio_timeline.py" "$@"
    ;;
  synthesize)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/audio_production.py" synthesize "$@"
    ;;
  voice-audition)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/audio_production.py" audition "$@"
    ;;
  replace-audio)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/pptx_production.py" replace-audio "$@"
    ;;
  assemble-pptx)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/pptx_production.py" assemble-pptx "$@"
    ;;
  export-video)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/powerpoint_production.py" export-video "$@"
    ;;
  export-pages)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/powerpoint_production.py" export-pages "$@"
    ;;
  qa)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/qa_presentation.py" "$@"
    ;;
  rebuild)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/rebuild_presentation.py" "$@"
    ;;
  validate)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/validate_project.py" "$@"
    ;;
  help|-h|--help)
    cat <<'USAGE'
Usage:
  scripts/run.sh bootstrap
  scripts/run.sh doctor [--stage static|audio|video]
  scripts/run.sh inspect-input --document source.md --markdown-output input-preflight.md
  scripts/run.sh prepare-input-review --document source.md --output input-review.json
  scripts/run.sh validate-input --document source.md [--review input-review.json] --json-output input-gate.json --markdown-output input-gate.md
  scripts/run.sh refresh-input-gate --project /path/to/project [--input-profile auto|page-narration|narrative-plan|execution-plan|presentation-source] [--input-review input-review.json]
  scripts/run.sh init --output /path/to/project --name "Project" --deliverable narration_audio|static_pptx|animated_pptx|narrated_pptx|video --input-document source.md [--input-review input-review.json] [--page-script-source page-script.md] [--allow-substantial-rewrite]
  scripts/run.sh approve --project /path/to/project --stage content|visual|narration --approved-by NAME [--pages 3,7,10] [--allow-substantial-rewrite]
  scripts/run.sh prepare-narration --project /path/to/project [--chapter-max-seconds 240] [--performance-plan plan.json] [--force]
  scripts/run.sh manifest [--visual animation_manifest.json] --director narration_director.json --voice-profile voice_profile.json --output animation_manifest.json --review narration_review.md
  scripts/run.sh configure-voice --project /path/to/project [--voice voice-name] [--rate +0%] [--pitch +0st] [--pronunciation-file glossary.json] [--replace-pronunciations]
  scripts/run.sh timing --manifest animation_manifest.json --output fast_animation_timing.json
  scripts/run.sh timing --manifest animation_manifest.json --output fast_animation_timing.json --check
  scripts/run.sh audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json
  scripts/run.sh audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json --check
  scripts/run.sh voice-audition --project /path/to/project --voices voice-a,voice-b [--dry-run]
  scripts/run.sh synthesize --project /path/to/project [--pages 1-3] [--dry-run]
  scripts/run.sh replace-audio --project /path/to/project
  scripts/run.sh assemble-pptx --project /path/to/project [--adapter command]
  scripts/run.sh export-video --project /path/to/project
  scripts/run.sh export-pages --project /path/to/project --pages 8,9,14 --format pdf --output selected.pdf
  scripts/run.sh qa --project /path/to/project --level static|audio|standard|release
  scripts/run.sh rebuild --project /path/to/project --scope audio --qa standard [--voice voice-name]
  scripts/run.sh validate --project /path/to/project [--stage content|visual|animation|narration|audio] [--strict]
USAGE
    ;;
  *)
    echo "Error: unknown command: ${COMMAND}" >&2
    exit 1
    ;;
esac
