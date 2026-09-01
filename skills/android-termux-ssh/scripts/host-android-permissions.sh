#!/usr/bin/env bash
set -u -o pipefail

ADB_BIN=${ADB:-adb}
SERIAL=
DO_STORAGE=0
DO_API=0
DO_BACKGROUND=0
DO_HYPEROS=0
APPLY=0
failures=0
EXTRA_KEEP_PACKAGES=()

usage() {
  cat <<'EOF'
Usage: host-android-permissions.sh [options]

Options:
  --adb PATH          adb executable (default: $ADB or adb)
  --serial SERIAL     target device serial
  --storage           grant Termux shared-storage access
  --api               grant common Termux:API camera/location/notification access
  --background        add Termux packages to DeviceIdle and standard background AppOps
  --hyperos-greeze    merge all Termux package names into MILLET_NO_RESTRICT_APP
  --keep-package PKG  also keep a dependent package such as the device VPN; repeatable
  --all-standard      same as --storage --api --background
  --apply             perform changes; without this flag only print the plan
  -h, --help          show this help

The HyperOS option is vendor-specific. Use it only after logs confirm Greeze freezing.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adb) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ADB_BIN=$2; shift 2 ;;
    --serial) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; SERIAL=$2; shift 2 ;;
    --storage) DO_STORAGE=1; shift ;;
    --api) DO_API=1; shift ;;
    --background) DO_BACKGROUND=1; shift ;;
    --hyperos-greeze) DO_HYPEROS=1; shift ;;
    --keep-package)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      [[ "$2" =~ ^[A-Za-z0-9._-]+$ ]] || { printf 'ERROR: invalid package name: %s\n' "$2" >&2; exit 2; }
      EXTRA_KEEP_PACKAGES+=("$2")
      shift 2
      ;;
    --all-standard) DO_STORAGE=1; DO_API=1; DO_BACKGROUND=1; shift ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

(( DO_STORAGE || DO_API || DO_BACKGROUND || DO_HYPEROS )) || { printf 'ERROR: select at least one change group\n' >&2; usage >&2; exit 2; }
command -v "$ADB_BIN" >/dev/null 2>&1 || { printf 'ERROR: adb not found: %s\n' "$ADB_BIN" >&2; exit 2; }
ADB_CMD=("$ADB_BIN")
[[ -n "$SERIAL" ]] && ADB_CMD+=(-s "$SERIAL")
state=$("${ADB_CMD[@]}" get-state 2>/dev/null | tr -d '\r' || true)
[[ "$state" == device ]] || { printf 'ERROR: no usable adb device (state=%s)\n' "${state:-none}" >&2; exit 2; }

adb_shell() { "${ADB_CMD[@]}" shell "$@" | tr -d '\r'; }
adb_shell_script() { printf '%s\n' "$1" | "${ADB_CMD[@]}" shell sh | tr -d '\r'; }
package_exists() { adb_shell pm path "$1" 2>/dev/null | grep -q '^package:'; }

printf 'Target: %s %s (serial=%s)\n' \
  "$(adb_shell getprop ro.product.manufacturer)" \
  "$(adb_shell getprop ro.product.model)" \
  "${SERIAL:-auto}"
printf 'Requested changes:\n'
(( DO_STORAGE )) && printf '  - Termux shared-storage permissions/AppOp\n'
(( DO_API )) && printf '  - Termux:API camera, location, notification, and overlay permissions/AppOps\n'
(( DO_BACKGROUND )) && printf '  - package-scoped DeviceIdle/background/wake-lock allowances\n'
(( DO_HYPEROS )) && printf '  - vendor setting MILLET_NO_RESTRICT_APP, preserving existing entries\n'
(( ${#EXTRA_KEEP_PACKAGES[@]} )) && printf '  - dependent keep-alive packages: %s\n' "${EXTRA_KEEP_PACKAGES[*]}"

if (( APPLY == 0 )); then
  printf '\nPreview only. Re-run with --apply after the user authorizes these changes.\n'
  exit 0
fi

run_optional() {
  local description=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK   %s\n' "$description"
  else
    printf 'WARN %s (unsupported or denied on this Android build)\n' "$description" >&2
    failures=$((failures + 1))
  fi
}

grant_permission() {
  local package_name=$1 permission=$2
  run_optional "$package_name $permission" adb_shell pm grant "$package_name" "$permission"
}

if (( DO_STORAGE )); then
  package_exists com.termux || { printf 'ERROR: com.termux is not installed\n' >&2; exit 1; }
  grant_permission com.termux android.permission.READ_EXTERNAL_STORAGE
  grant_permission com.termux android.permission.WRITE_EXTERNAL_STORAGE
  run_optional 'com.termux MANAGE_EXTERNAL_STORAGE AppOp' adb_shell appops set com.termux MANAGE_EXTERNAL_STORAGE allow
fi

if (( DO_API )); then
  package_exists com.termux.api || { printf 'ERROR: com.termux.api is not installed\n' >&2; exit 1; }
  grant_permission com.termux.api android.permission.CAMERA
  grant_permission com.termux.api android.permission.ACCESS_COARSE_LOCATION
  grant_permission com.termux.api android.permission.ACCESS_FINE_LOCATION
  grant_permission com.termux.api android.permission.ACCESS_BACKGROUND_LOCATION
  grant_permission com.termux.api android.permission.POST_NOTIFICATIONS
  run_optional 'com.termux.api SYSTEM_ALERT_WINDOW AppOp' adb_shell appops set com.termux.api SYSTEM_ALERT_WINDOW allow
fi

if (( DO_BACKGROUND )); then
  for package_name in com.termux com.termux.api com.termux.boot io.github.scisaga.termuxbluetoothbridge "${EXTRA_KEEP_PACKAGES[@]}"; do
    package_exists "$package_name" || continue
    run_optional "$package_name DeviceIdle whitelist" adb_shell cmd deviceidle whitelist "+$package_name"
    run_optional "$package_name RUN_IN_BACKGROUND AppOp" adb_shell appops set "$package_name" RUN_IN_BACKGROUND allow
    run_optional "$package_name RUN_ANY_IN_BACKGROUND AppOp" adb_shell appops set "$package_name" RUN_ANY_IN_BACKGROUND allow
    run_optional "$package_name WAKE_LOCK AppOp" adb_shell appops set "$package_name" WAKE_LOCK allow
  done
fi

if (( DO_HYPEROS )); then
  manufacturer=$(adb_shell getprop ro.product.manufacturer)
  if [[ "${manufacturer,,}" != *xiaomi* && "${manufacturer,,}" != *redmi* ]]; then
    printf 'WARN manufacturer is %s; MILLET setting may be unused\n' "$manufacturer" >&2
  fi
  current=$(adb_shell settings get system MILLET_NO_RESTRICT_APP 2>/dev/null || true)
  [[ "$current" == null ]] && current=
  merged=
  add_entry() {
    local entry=$1
    [[ -n "$entry" ]] || return 0
    if [[ ! "$entry" =~ ^[A-Za-z0-9._-]+$ ]]; then
      printf 'WARN ignoring malformed MILLET entry: %s\n' "$entry" >&2
      failures=$((failures + 1))
      return 0
    fi
    case ",$merged," in
      *",$entry,"*) ;;
      *) merged=${merged:+$merged,}$entry ;;
    esac
  }
  IFS=',' read -r -a existing_entries <<<"$current"
  for entry in "${existing_entries[@]}"; do
    entry=${entry//[[:space:]]/}
    add_entry "$entry"
  done
  for package_name in com.termux com.termux.api com.termux.boot io.github.scisaga.termuxbluetoothbridge "${EXTRA_KEEP_PACKAGES[@]}"; do
    package_exists "$package_name" && add_entry "$package_name"
  done
  # PowerKeeper serializes its no-restrict set as "pkg.one, pkg.two". Send the
  # command over stdin so adb.exe invoked from WSL cannot split the value at
  # spaces before Android's shell receives it.
  merged_display=${merged//,/, }
  if adb_shell_script "settings put system MILLET_NO_RESTRICT_APP '$merged_display'" >/dev/null; then
    printf 'OK   MILLET_NO_RESTRICT_APP=%s\n' "$(adb_shell settings get system MILLET_NO_RESTRICT_APP)"
  else
    printf 'ERROR could not update MILLET_NO_RESTRICT_APP\n' >&2
    failures=$((failures + 1))
  fi
fi

printf '\nApplied with %d warning(s). Verify real storage/API/lock-screen behavior next.\n' "$failures"
