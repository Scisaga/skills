#!@PREFIX@/bin/bash
# Managed by standalone_code.py
set -euo pipefail
umask 077

prefix=@PREFIX_SHELL@
container=@CONTAINER@
user=@USER@
display=@DISPLAY@
scale=@SCALE@
tag=vscode
x11_args=(@X11_ARGS@)
code_args=(@CODE_ARGS@)
activity=com.termux.x11/com.termux.x11.MainActivity
export PATH="$prefix/bin:/system/bin"
export TMPDIR="$prefix/tmp"
state="$HOME/.local/state/tablet-desktop/vscode-standalone"
socket_path="$TMPDIR/.X11-unix/X${display#:}"
lock_path="$TMPDIR/.X${display#:}-lock"

mkdir -p "$state"
exec 9>"$state/session.lock"
if ! flock -n 9; then
    exec "$prefix/bin/am" start --user 0 -n "$activity" -d "$tag"
fi

exec >"$state/last.log" 2>&1
if [[ -e "$socket_path" || -L "$socket_path" || -e "$lock_path" || -L "$lock_path" ]]; then
    printf 'Display %s already has a socket or lock. Inspect its owner.\n' "$display" >&2
    exit 1
fi

server_pid=
socket_identity=
lock_identity=
remember_display() {
    if [[ -f "$lock_path" && -O "$lock_path" && ! -L "$lock_path" &&
          -S "$socket_path" && -O "$socket_path" && ! -L "$socket_path" &&
          "$(tr -d '[:space:]' <"$lock_path")" == "$server_pid" ]]; then
        socket_identity=$(stat -c '%d:%i' "$socket_path")
        lock_identity=$(stat -c '%d:%i' "$lock_path")
    fi
}

close_display() {
    if [[ -n "$server_pid" ]]; then
        remember_display
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
        if [[ -n "$socket_identity" && "$(stat -c '%d:%i' "$socket_path" 2>/dev/null || true)" == "$socket_identity" ]]; then
            rm -f -- "$socket_path"
        fi
        if [[ -n "$lock_identity" && "$(stat -c '%d:%i' "$lock_path" 2>/dev/null || true)" == "$lock_identity" ]]; then
            rm -f -- "$lock_path"
        fi
        "$prefix/bin/am" broadcast --user 0 -a com.termux.x11.ACTION_STOP -p com.termux.x11 \
            --es document_tag "$tag" >/dev/null 2>&1 || true
    fi
}

trap close_display EXIT
trap 'exit 130' HUP INT TERM
unset TERMUX_X11_XSTARTUP
"$prefix/bin/termux-x11" "$display" -tag "$tag" -nolisten tcp "${x11_args[@]}" 9>&- &
server_pid=$!
for attempt in {1..50}; do
    kill -0 "$server_pid" 2>/dev/null || { printf '%s\n' 'The tagged X11 server exited.' >&2; exit 1; }
    if [[ -S "$socket_path" ]] && DISPLAY="$display" xprop -root >/dev/null 2>&1; then
        break
    fi
    sleep .2
done
DISPLAY="$display" xprop -root >/dev/null 2>&1 || { printf '%s\n' 'The tagged X11 display was not ready.' >&2; exit 1; }
remember_display
"$prefix/bin/am" start --user 0 -n "$activity" -d "$tag"

"$prefix/bin/proot-distro" login "$container" --user "$user" --shared-tmp -- \
    /bin/bash -s -- "$display" "$scale" "${code_args[@]}" 9>&- <<'GUEST'
set -euo pipefail
umask 077
root="$HOME/.local/share/tablet-vscode"
export DISPLAY="$1" GDK_SCALE="$2" GDK_DPI_SCALE=1 XDG_SESSION_TYPE=x11
shift 2
export GDK_GL=disable NO_AT_BRIDGE=1
export XDG_CONFIG_HOME="$root/config" XDG_DATA_HOME="$root/data" XDG_CACHE_HOME="$root/cache" XDG_RUNTIME_DIR="$root/run"
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS DBUS_STARTER_ADDRESS DBUS_STARTER_BUS_TYPE
unset WAYLAND_DISPLAY GDK_CORE_DEVICE_EVENTS ELECTRON_RUN_AS_NODE VSCODE_IPC_HOOK_CLI BROWSER XDG_CURRENT_DESKTOP DESKTOP_SESSION
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR" "$root/code/User" "$root/extensions"
settings="$root/code/User/settings.json"
if [[ ! -e "$settings" && ! -L "$settings" ]]; then
    (set -o noclobber; printf '%s\n' '{"window.newWindowDimensions":"maximized"}' >"$settings")
fi
export VSCODE_STANDALONE_HOME="$root"

exec /usr/bin/dbus-run-session -- /bin/bash -s -- "$@" <<'SESSION'
    set -euo pipefail
    /usr/bin/xfwm4 --compositor=off --vblank=off &
    wm_pid=$!
    close_wm() {
        kill "$wm_pid" 2>/dev/null || true
        wait "$wm_pid" 2>/dev/null || true
    }
    trap close_wm EXIT
    for attempt in {1..40}; do
        kill -0 "$wm_pid" 2>/dev/null || { printf "%s\n" "The window manager exited." >&2; exit 1; }
        if /usr/bin/xprop -root _NET_SUPPORTING_WM_CHECK | grep -q "window id #"; then
            break
        fi
        sleep .2
    done
    /usr/bin/xprop -root _NET_SUPPORTING_WM_CHECK | grep -q "window id #" || exit 1
@CODE_GUARD@
    if [[ -f "$HOME/.local/share/tablet-desktop/android-keyring/master.sealed" ]]; then
        set -- "$@" --password-store=gnome-libsecret
    fi
    "$@" --user-data-dir "$VSCODE_STANDALONE_HOME/code" --extensions-dir "$VSCODE_STANDALONE_HOME/extensions"
SESSION
GUEST
