#!/usr/bin/env bash
# Both systemd roles use pinned binaries from the same version directory.

readonly HY2_BIN_ROOT="/usr/local/libexec/scisaga/hysteria"
readonly HY2_LEGACY_BINARY="/usr/local/bin/hysteria"
readonly HY2_DEFAULT_VERSION="2.8.1"

prompt_value() {
  local name="$1"
  local prompt="$2"
  local hidden="${3:-false}"

  [ -n "${!name:-}" ] && return 0

  if [ "${hidden}" = "true" ]; then
    read -r -s -p "${prompt}: " "${name}"
    printf '\n'
  else
    read -r -p "${prompt}: " "${name}"
  fi
}

install_hysteria_binary() (
  set -e
  local version="$1"
  [[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]] || die "invalid Hysteria version: ${version}"

  local directory="${HY2_BIN_ROOT}/${version}"
  local binary="${directory}/hysteria"
  local arch artifact staged
  if [[ ! -f "${binary}" || ! -x "${binary}" ]]; then
    arch="$(uname -m)"
    case "${arch}" in
      x86_64) artifact="hysteria-linux-amd64" ;;
      aarch64|arm64) artifact="hysteria-linux-arm64" ;;
      *) die "unsupported architecture: ${arch}" ;;
    esac
    sudo install -d -- "${directory}"
    staged="$(sudo mktemp "${directory}/.download.XXXXXX")"
    trap 'sudo rm -f -- "${staged}"' EXIT
    trap 'exit 130' HUP INT TERM
    sudo curl -fsSL "https://github.com/apernet/hysteria/releases/download/app%2Fv${version}/${artifact}" -o "${staged}"
    [[ -s "${staged}" ]] || die "empty Hysteria download for ${version}"
    sudo chmod 0755 "${staged}"
    if ! sudo ln -T -- "${staged}" "${binary}" 2>/dev/null; then
      [[ -f "${binary}" && -x "${binary}" ]] || die "cannot publish the Hysteria binary at ${binary}"
    fi
  fi

  if [[ ! -e "${HY2_LEGACY_BINARY}" && ! -L "${HY2_LEGACY_BINARY}" ]]; then
    if ! sudo ln -sT -- "${binary}" "${HY2_LEGACY_BINARY}" 2>/dev/null; then
      [[ -e "${HY2_LEGACY_BINARY}" || -L "${HY2_LEGACY_BINARY}" ]] || die "cannot create ${HY2_LEGACY_BINARY}"
    fi
  fi
  printf '%s\n' "${binary}"
)
