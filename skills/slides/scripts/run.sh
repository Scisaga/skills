#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf -v RUN_COMMAND 'bash %q' "${SCRIPT_DIR}/run.sh"
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
  exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
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
  list-voices)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/audio_production.py" list-voices "$@"
    ;;
  replace-audio)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/html_production.py" --replace-audio "$@"
    ;;
  assemble-html)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/html_production.py" "$@"
    ;;
  export-video)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/html_export.py" export-video "$@"
    ;;
  export-pages)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/html_export.py" export-pages "$@"
    ;;
  migrate-html)
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/migrate_html.py" "$@"
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
    cat <<USAGE
Usage:
  ${RUN_COMMAND} bootstrap [--stage static|audio|narrated|video|all]
  ${RUN_COMMAND} doctor [--stage static|audio|narrated|video|all]
  ${RUN_COMMAND} inspect-input --document source.md --markdown-output input-preflight.md
  ${RUN_COMMAND} prepare-input-review --document source.md --output input-review.json
  ${RUN_COMMAND} validate-input --document source.md [--review input-review.json] --json-output input-gate.json --markdown-output input-gate.md
  ${RUN_COMMAND} refresh-input-gate --project /path/to/project [--input-profile auto|page-narration|narrative-plan|execution-plan|presentation-source] [--input-review input-review.json]
  ${RUN_COMMAND} init --output /path/to/project --name "Project" --deliverable narration_audio|static_html|animated_html|narrated_html --input-document source.md [--input-review input-review.json] [--page-script-source page-script.md] [--template-source theme.css] [--seconds-per-page N] [--allow-substantial-rewrite]
  ${RUN_COMMAND} approve --project /path/to/project --stage content|visual|narration --approved-by NAME [--pages 3,7,10] [--allow-substantial-rewrite]
  ${RUN_COMMAND} prepare-narration --project /path/to/project [--chapter-max-seconds 240] [--performance-plan plan.json] [--force]
  ${RUN_COMMAND} manifest [--visual animation_manifest.json] --director narration_director.json --voice-profile voice_profile.json --output animation_manifest.json --review narration_review.md
  ${RUN_COMMAND} list-voices
  ${RUN_COMMAND} configure-voice --project /path/to/project [--provider auto|qwen3-tts-openai|azure-speech] [--qwen-voice VOICE_ID] [--voice azure-voice-name] [--rate +0%] [--pitch +0st] [--pronunciation-file glossary.json] [--replace-pronunciations]
  ${RUN_COMMAND} timing --manifest animation_manifest.json --output fast_animation_timing.json
  ${RUN_COMMAND} timing --manifest animation_manifest.json --output fast_animation_timing.json --check
  ${RUN_COMMAND} audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json
  ${RUN_COMMAND} audio-timeline --manifest animation_manifest.json --audio-dir audio --output audio_timeline.json --check
  ${RUN_COMMAND} voice-audition --project /path/to/project [--provider qwen3-tts-openai|azure-speech] [--voices voice-a,voice-b] [--dry-run]
  ${RUN_COMMAND} synthesize --project /path/to/project [--pages 1-3] [--dry-run]
  ${RUN_COMMAND} replace-audio --project /path/to/project
  ${RUN_COMMAND} assemble-html --project /path/to/project
  ${RUN_COMMAND} export-video --project /path/to/project
  ${RUN_COMMAND} export-pages --project /path/to/project [--pages 8,9,14] --format pdf|png|jpg --output selected.pdf
  ${RUN_COMMAND} migrate-html --project OLD --output NEW [--template-source theme.css]
  ${RUN_COMMAND} qa --project /path/to/project --level static|audio|standard
  ${RUN_COMMAND} rebuild --project /path/to/project --scope audio --qa standard [--voice voice-name]
  ${RUN_COMMAND} validate --project /path/to/project [--stage content|visual|animation|narration|audio] [--strict]
USAGE
    ;;
  *)
    echo "Error: unknown command: ${COMMAND}" >&2
    exit 1
    ;;
esac
