#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON_POSIX="$ROOT_DIR/.venv/bin/python"
VENV_PYTHON_WINDOWS="$ROOT_DIR/.venv/Scripts/python.exe"

is_runnable_python() {
  local candidate="$1"
  [ -n "${candidate}" ] || return 1
  [ -f "${candidate}" ] || return 1
  "${candidate}" --version >/dev/null 2>&1
}

if is_runnable_python "$VENV_PYTHON_POSIX"; then
  PYTHON_BIN="$VENV_PYTHON_POSIX"
elif is_runnable_python "$VENV_PYTHON_WINDOWS"; then
  PYTHON_BIN="$VENV_PYTHON_WINDOWS"
elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "错误：未找到 python3 或 python。" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
用法:
  bash skills/pdf/scripts/run.sh replace-page <src_pdf> <repl_pdf> <page> <out_pdf>
  bash skills/pdf/scripts/run.sh overlay-watermark <src_pdf> <out_pdf> [args...]
  bash skills/pdf/scripts/run.sh watermark <src_pdf> <out_pdf> [args...]
  bash skills/pdf/scripts/run.sh seam-seal <input_pdf> <seal_png> <output_pdf> [args...]
  bash skills/pdf/scripts/run.sh page-ops <subcommand> [args...]
  bash skills/pdf/scripts/run.sh images-to-pdf <output_pdf> <img1> <img2> ...
  bash skills/pdf/scripts/run.sh pdf-to-images <input_pdf> <output_dir> [args...]
  bash skills/pdf/scripts/run.sh batch <subcommand> [args...]
  bash skills/pdf/scripts/run.sh doctor
  bash skills/pdf/scripts/run.sh bootstrap
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

command_name="$1"
shift

case "$command_name" in
  replace-page|replace)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_page_replace.py" "$@"
    ;;
  overlay-watermark|watermark-overlay|visible-watermark)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_overlay_watermark.py" "$@"
    ;;
  watermark|rasterize-watermark|rasterize)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_to_image_pdf_with_watermark.py" "$@"
    ;;
  seam-seal|seal)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/add_qifeng_seal.py" "$@"
    ;;
  page-ops|pages)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_page_ops.py" "$@"
    ;;
  images-to-pdf)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_image_convert.py" images-to-pdf "$@"
    ;;
  pdf-to-images|export-images)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_image_convert.py" pdf-to-images "$@"
    ;;
  batch)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/pdf_batch.py" "$@"
    ;;
  doctor|check)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/doctor.py" "$@"
    ;;
  bootstrap)
    exec "$SCRIPT_DIR/bootstrap.sh" "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "错误：未知命令 $command_name" >&2
    usage
    exit 1
    ;;
esac
