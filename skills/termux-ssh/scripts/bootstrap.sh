#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

SSH_PORT=8022
LOGIN_LABEL=root
HOST_LABEL=android
SSH_START_DIRECTORY=
SHARED_WORKSPACE=
AUTHORIZED_KEY_FILE=
AUTHORIZED_KEY_STDIN=0
WITH_API=1
WITH_BASH=1
WITH_STORAGE=1
SKIP_PACKAGES=0
TEMP_KEY_FILE=
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
AGENTS_HELPER="$SCRIPT_DIR/update-agents-md.sh"

usage() {
  cat <<'EOF'
Usage: bootstrap.sh [options]

Run this script inside Termux.

Options:
  --authorized-key-file PATH  Import one or more plain OpenSSH public-key lines
  --authorized-key-stdin      Read public-key lines from standard input
  --ssh-port PORT             SSH port (default: 8022; unprivileged devices cannot use <1024)
  --login-label NAME          Cosmetic SSH/prompt user label (default: root)
  --host-label NAME           Cosmetic prompt host label (default: android)
  --ssh-start-directory PATH  Initial directory for interactive SSH; keeps HOME private
  --shared-workspace PATH     Expose PATH as ~/workspace without changing login directory
  --without-api               Do not install Termux:API CLI or camera/Wi-Fi helpers
  --without-bash              Do not install/configure Ubuntu-style Bash interaction
  --without-storage-links     Do not create standard ~/storage links when access exists
  --skip-packages             Do not run apt update/install
  -h, --help                  Show this help

If authorized_keys already contains a key, --authorized-key-* is optional.
Never provide a private key to this script.
Keep update-agents-md.sh in the same directory; bootstrap installs it as update-termux-agents.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

cleanup() {
  if [[ -n "$TEMP_KEY_FILE" && -f "$TEMP_KEY_FILE" ]]; then
    unlink "$TEMP_KEY_FILE"
  fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --authorized-key-file)
      [[ $# -ge 2 ]] || die "$1 requires a path"
      AUTHORIZED_KEY_FILE=$2
      shift 2
      ;;
    --authorized-key-stdin) AUTHORIZED_KEY_STDIN=1; shift ;;
    --ssh-port)
      [[ $# -ge 2 ]] || die "$1 requires a port"
      SSH_PORT=$2
      shift 2
      ;;
    --login-label)
      [[ $# -ge 2 ]] || die "$1 requires a name"
      LOGIN_LABEL=$2
      shift 2
      ;;
    --host-label)
      [[ $# -ge 2 ]] || die "$1 requires a name"
      HOST_LABEL=$2
      shift 2
      ;;
    --ssh-start-directory)
      [[ $# -ge 2 ]] || die "$1 requires a path"
      SSH_START_DIRECTORY=$2
      shift 2
      ;;
    --shared-workspace)
      [[ $# -ge 2 ]] || die "$1 requires a path"
      SHARED_WORKSPACE=$2
      shift 2
      ;;
    --without-api) WITH_API=0; shift ;;
    --without-bash) WITH_BASH=0; shift ;;
    --without-storage-links) WITH_STORAGE=0; shift ;;
    --skip-packages) SKIP_PACKAGES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ ${PREFIX:-} == */com.termux/files/usr ]] || die "this script must run inside the standard Termux environment"
[[ -x "$PREFIX/bin/bash" ]] || die "Termux bash is unavailable"
[[ -r "$AGENTS_HELPER" ]] || die "missing companion script: $AGENTS_HELPER"
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "SSH port must be numeric"
(( SSH_PORT >= 1 && SSH_PORT <= 65535 )) || die "SSH port must be between 1 and 65535"
if (( SSH_PORT < 1024 )) && (( $(id -u) != 0 )); then
  die "port $SSH_PORT is privileged; use 8022 on a non-rooted device"
fi
[[ "$LOGIN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || die "login label contains unsupported characters"
[[ "$HOST_LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || die "host label contains unsupported characters"
if [[ -n "$SSH_START_DIRECTORY" ]]; then
  [[ "$SSH_START_DIRECTORY" == /* ]] || die "SSH start directory must be an absolute path"
  (( WITH_BASH == 1 )) || die "--ssh-start-directory requires Bash configuration"
fi
if [[ -n "$SHARED_WORKSPACE" ]]; then
  [[ "$SHARED_WORKSPACE" == /* ]] || die "shared workspace must be an absolute path"
fi
if [[ -n "$AUTHORIZED_KEY_FILE" && $AUTHORIZED_KEY_STDIN -eq 1 ]]; then
  die "choose either --authorized-key-file or --authorized-key-stdin"
fi

if (( SKIP_PACKAGES == 0 )); then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  dpkg --force-confold --configure -a
  packages=(
    openssh termux-services bash coreutils less procps findutils grep sed gawk
    diffutils file which iproute2 bash-completion command-not-found man nano vim
    htop tree git
  )
  if (( WITH_API == 1 )); then packages+=(termux-api); fi
  apt-get -o Dpkg::Options::="--force-confold" -y install "${packages[@]}"
fi

for required in sshd ssh-keygen sv sv-enable; do
  command -v "$required" >/dev/null 2>&1 || die "missing command after package setup: $required"
done

install -d -m 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"

if (( AUTHORIZED_KEY_STDIN == 1 )); then
  TEMP_KEY_FILE=$(mktemp "$PREFIX/tmp/android-termux-key.XXXXXX")
  chmod 600 "$TEMP_KEY_FILE"
  sed 's/\r$//' > "$TEMP_KEY_FILE"
  AUTHORIZED_KEY_FILE=$TEMP_KEY_FILE
fi

if [[ -n "$AUTHORIZED_KEY_FILE" ]]; then
  [[ -f "$AUTHORIZED_KEY_FILE" ]] || die "public-key file not found: $AUTHORIZED_KEY_FILE"
  added=0
  while IFS= read -r key_line || [[ -n "$key_line" ]]; do
    key_line=${key_line%$'\r'}
    [[ -z "$key_line" || "$key_line" == \#* ]] && continue
    case "$key_line" in
      ssh-*|ecdsa-*|sk-*) ;;
      *) die "key file contains a non-public-key line; use plain OpenSSH public keys only" ;;
    esac
    if ! grep -Fqx -- "$key_line" "$HOME/.ssh/authorized_keys"; then
      printf '%s\n' "$key_line" >> "$HOME/.ssh/authorized_keys"
      added=$((added + 1))
    fi
  done < "$AUTHORIZED_KEY_FILE"
  printf 'Authorized keys added: %d\n' "$added"
fi

[[ -s "$HOME/.ssh/authorized_keys" ]] || die "authorized_keys is empty; provide a host public key before disabling passwords"
ssh-keygen -lf "$HOME/.ssh/authorized_keys" >/dev/null || die "authorized_keys does not contain a valid OpenSSH public key"

install -d -m 700 "$PREFIX/etc/ssh/sshd_config.d"
cat > "$PREFIX/etc/ssh/sshd_config.d/20-android-termux-ssh.conf" <<EOF
# Managed by android-termux-ssh.
Port $SSH_PORT
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
ClientAliveInterval 60
ClientAliveCountMax 3
EOF
chmod 600 "$PREFIX/etc/ssh/sshd_config.d/20-android-termux-ssh.conf"
sshd -t || die "sshd configuration validation failed"

install -d -m 700 "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start-sshd" <<EOF
#!$PREFIX/bin/sh
termux-wake-lock
export SVDIR=$PREFIX/var/service
. $PREFIX/etc/profile.d/start-services.sh
sleep 2
sv-enable sshd
sv up $PREFIX/var/service/sshd
EOF
chmod 700 "$HOME/.termux/boot/start-sshd"

if (( WITH_API == 1 )); then
  cat > "$PREFIX/bin/remote-camera-photo" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
set -eu
output=${1:-"$HOME/camera-$(date +%Y%m%d-%H%M%S).jpg"}
camera=${2:-0}
am start -n com.termux/.app.TermuxActivity >/dev/null
sleep 2
termux-camera-photo -c "$camera" "$output"
if [ ! -s "$output" ]; then
  echo "camera capture failed" >&2
  exit 1
fi
printf '%s\n' "$output"
EOF
  chmod 755 "$PREFIX/bin/remote-camera-photo"

  cat > "$PREFIX/bin/remote-wifi-scan" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec termux-wifi-scaninfo
EOF
  chmod 755 "$PREFIX/bin/remote-wifi-scan"

  cat > "$PREFIX/bin/remote-bluetooth-settings" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
set -eu
exec am start -a android.settings.BLUETOOTH_SETTINGS
EOF
  chmod 755 "$PREFIX/bin/remote-bluetooth-settings"
fi

if (( WITH_STORAGE == 1 )) && [[ -r /storage/emulated/0 && -x /storage/emulated/0 ]]; then
  install -d -m 700 "$HOME/storage"
  make_link() {
    local target=$1 link=$2
    if [[ -e "$link" || -L "$link" ]]; then return 0; fi
    ln -s "$target" "$link"
  }
  make_link /storage/emulated/0 "$HOME/storage/shared"
  make_link /storage/emulated/0/Download "$HOME/storage/downloads"
  make_link /storage/emulated/0/DCIM "$HOME/storage/dcim"
  make_link /storage/emulated/0/Pictures "$HOME/storage/pictures"
  make_link /storage/emulated/0/Music "$HOME/storage/music"
  make_link /storage/emulated/0/Movies "$HOME/storage/movies"
elif (( WITH_STORAGE == 1 )); then
  warn "shared storage is not accessible; grant Android storage access and run termux-setup-storage"
fi

if [[ -n "$SHARED_WORKSPACE" ]]; then
  mkdir -p -- "$SHARED_WORKSPACE"
  [[ -d "$SHARED_WORKSPACE" && -r "$SHARED_WORKSPACE" \
    && -w "$SHARED_WORKSPACE" && -x "$SHARED_WORKSPACE" ]] || \
    die "shared workspace is not fully accessible: $SHARED_WORKSPACE"
  workspace_link="$HOME/workspace"
  if [[ -L "$workspace_link" ]]; then
    [[ "$(readlink -f -- "$workspace_link")" == "$(readlink -f -- "$SHARED_WORKSPACE")" ]] || \
      die "existing ~/workspace points somewhere else: $(readlink -- "$workspace_link")"
  elif [[ -e "$workspace_link" ]]; then
    die "~/workspace already exists and is not a symlink"
  else
    ln -s -- "$SHARED_WORKSPACE" "$workspace_link"
  fi
  if command -v git >/dev/null 2>&1 \
      && [[ "$SHARED_WORKSPACE" == /storage/emulated/0/* ]]; then
    git_safe_directory="$SHARED_WORKSPACE/*"
    if ! git config --global --get-all safe.directory 2>/dev/null \
        | grep -Fqx -- "$git_safe_directory"; then
      git config --global --add safe.directory "$git_safe_directory"
    fi
  fi
fi

ensure_line() {
  local file=$1 line=$2
  touch "$file"
  if ! grep -Fqx -- "$line" "$file"; then
    printf '\n%s\n' "$line" >> "$file"
  fi
}

if (( WITH_BASH == 1 )); then
  managed_dir="$HOME/.config/android-termux-ssh"
  install -d -m 700 "$managed_dir"
  {
    printf "TERMUX_PROMPT_USER='%s'\n" "$LOGIN_LABEL"
    printf "TERMUX_PROMPT_HOST='%s'\n" "$HOST_LABEL"
    cat <<'EOF'

[[ $- != *i* ]] && return

export EDITOR=nano VISUAL=nano PAGER=less LESS='-RF'
export SVDIR="$PREFIX/var/service"
HISTCONTROL=ignoreboth:erasedups
HISTSIZE=10000
HISTFILESIZE=20000
HISTTIMEFORMAT='%F %T '
shopt -s histappend histverify checkwinsize cmdhist
shopt -s globstar 2>/dev/null || true
case ";${PROMPT_COMMAND:-};" in
  *";history -a;"*) ;;
  *) PROMPT_COMMAND="history -a${PROMPT_COMMAND:+; $PROMPT_COMMAND}" ;;
esac
if command -v dircolors >/dev/null 2>&1; then eval "$(dircolors -b 2>/dev/null)"; fi
alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias fgrep='fgrep --color=auto'
alias egrep='egrep --color=auto'
alias diff='diff --color=auto'
alias ll='ls -alF --group-directories-first'
alias la='ls -A --group-directories-first'
alias l='ls -CF --group-directories-first'
alias ..='cd ..'
alias ...='cd ../..'
alias cls='clear'
[[ -r "$HOME/.bash_aliases" ]] && . "$HOME/.bash_aliases"
if ! declare -F _completion_loader >/dev/null 2>&1; then
  [[ -r "$PREFIX/share/bash-completion/bash_completion" ]] &&
    . "$PREFIX/share/bash-completion/bash_completion"
fi
if [[ ${TERM:-dumb} != dumb ]]; then
  PS1="\[\e]0;${TERMUX_PROMPT_USER}@${TERMUX_PROMPT_HOST}: \w\a\]\[\e[01;32m\]${TERMUX_PROMPT_USER}@${TERMUX_PROMPT_HOST}\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]# "
else
  PS1="${TERMUX_PROMPT_USER}@${TERMUX_PROMPT_HOST}:\w# "
fi

# Keep HOME in Termux private storage, but optionally start interactive SSH
# sessions in a user-selected shared directory.
if [[ $- == *i* && -n "${SSH_CONNECTION:-}" ]]; then
  _termux_ssh_start_file="$HOME/.config/android-termux-ssh/ssh-start-directory"
  if [[ -r "$_termux_ssh_start_file" ]]; then
    IFS= read -r _termux_ssh_start_dir < "$_termux_ssh_start_file" || true
    if [[ "${_termux_ssh_start_dir:-}" == /* && -d "$_termux_ssh_start_dir" ]]; then
      cd -- "$_termux_ssh_start_dir"
    fi
  fi
  unset _termux_ssh_start_file _termux_ssh_start_dir
fi
EOF
  } > "$managed_dir/bashrc"
  chmod 600 "$managed_dir/bashrc"

  if [[ -n "$SSH_START_DIRECTORY" ]]; then
    mkdir -p -- "$SSH_START_DIRECTORY"
    [[ -d "$SSH_START_DIRECTORY" && -r "$SSH_START_DIRECTORY" \
      && -w "$SSH_START_DIRECTORY" && -x "$SSH_START_DIRECTORY" ]] || \
      die "SSH start directory is not fully accessible: $SSH_START_DIRECTORY"
    printf '%s\n' "$SSH_START_DIRECTORY" > "$managed_dir/ssh-start-directory"
    chmod 600 "$managed_dir/ssh-start-directory"

    # Android emulated storage reports a synthetic owner, so recent Git marks
    # repositories there as dubious unless the chosen subtree is trusted.
    if command -v git >/dev/null 2>&1 \
        && [[ "$SSH_START_DIRECTORY" == /storage/emulated/0/* ]]; then
      git_safe_directory="$SSH_START_DIRECTORY/*"
      if ! git config --global --get-all safe.directory 2>/dev/null \
          | grep -Fqx -- "$git_safe_directory"; then
        git config --global --add safe.directory "$git_safe_directory"
      fi
    fi
  fi

  cat > "$managed_dir/inputrc" <<'EOF'
set bell-style none
set completion-ignore-case on
set completion-map-case on
set show-all-if-ambiguous on
set colored-stats on
set visible-stats on
set mark-symlinked-directories on
"\e[A": history-search-backward
"\e[B": history-search-forward
"\e[5~": history-search-backward
"\e[6~": history-search-forward
EOF
  chmod 600 "$managed_dir/inputrc"

  ensure_line "$HOME/.bashrc" '[[ -r "$HOME/.config/android-termux-ssh/bashrc" ]] && . "$HOME/.config/android-termux-ssh/bashrc"'
  ensure_line "$HOME/.bash_profile" '[[ -r "$HOME/.bashrc" ]] && . "$HOME/.bashrc"'
  ensure_line "$HOME/.inputrc" "\$include $managed_dir/inputrc"
  bash -n "$HOME/.bashrc" "$HOME/.bash_profile" "$managed_dir/bashrc"
fi

export SVDIR="$PREFIX/var/service"
termux-wake-lock || warn "could not acquire wake lock; check the Termux foreground-service state"
. "$PREFIX/etc/profile.d/start-services.sh"
sleep 1
sv-enable sshd
sv up "$PREFIX/var/service/sshd"

install -m 755 "$AGENTS_HELPER" "$PREFIX/bin/update-termux-agents"
"$PREFIX/bin/update-termux-agents" \
  --ssh-port "$SSH_PORT" \
  --login-label "$LOGIN_LABEL" \
  --host-label "$HOST_LABEL"

printf '\nConfiguration complete.\n'
printf 'SSH: ssh -p %s %s@PHONE_IP\n' "$SSH_PORT" "$LOGIN_LABEL"
printf 'Actual Android user: %s (not UID 0 unless the device is truly rooted)\n' "$(whoami)"
printf 'Authorized key fingerprints:\n'
ssh-keygen -lf "$HOME/.ssh/authorized_keys"
printf '\nNext: open Termux:Boot once, grant Android permissions, then run verify-termux.sh.\n'
