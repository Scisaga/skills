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
slot=0
dock_tag=
fresh=0
workspace=
launch_request=
editor_token=
desktop_display=@DESKTOP_DISPLAY@
x11_args=(@X11_ARGS@)
code_args=(@CODE_ARGS@)
x11_command=(@X11_COMMAND@)
title_bridge=@TITLE_BRIDGE@
android_package=@ANDROID_PACKAGE@
activity="$android_package/com.termux.x11.MainActivity"
export PATH="$prefix/bin:/system/bin"
export TMPDIR="$prefix/tmp"
state="$HOME/@STATE_DIR@"

wait_for_android_window() (
    local ticket="$dock_state/requests/$launch_request"
    mkdir -p -- "$dock_state/requests"
    mkdir -- "$ticket"
    trap 'rm -f -- "$ticket/attached"; rmdir -- "$ticket"' EXIT
    "$prefix/bin/am" broadcast --user 0 -a "$android_package.WINDOW_READY" -p "$android_package" \
        --es launch_request "$launch_request" --es document_tag "$1" \
        --es editor_title "$2" --es editor_token "$3" >/dev/null
    for attempt in {1..80}; do
        [[ ! -f "$ticket/attached" ]] || exit 0
        sleep .1
    done
    printf '%s\n' 'The Android VSCode launch request was closed or timed out.' >&2
    exit 1
)

show_window() {
    local window_tag="$1" window_title="${2:-}" window_token="${3:-}"
    if [[ -n "$launch_request" ]]; then
        wait_for_android_window "$window_tag" "$window_title" "$window_token"
    else
        local args=(start --user 0 -n "$activity" -d "$window_tag")
        [[ -z "$window_title" ]] || args+=(--es editor_title "$window_title")
        "$prefix/bin/am" "${args[@]}"
    fi
}

mkdir -p "$state"
@WINDOW_SETUP@

socket_path="$TMPDIR/.X11-unix/X${display#:}"
lock_path="$TMPDIR/.X${display#:}-lock"

start_log() {
    local temporary payload_limit=$((4 * 1024 * 1024 - 96))
    if ! temporary=$(mktemp "$state/.last.log.XXXXXX"); then
        exec >/dev/null 2>&1
        return
    fi
    if ! mv -fT -- "$temporary" "$state/last.log"; then
        rm -f -- "$temporary"
        exec >/dev/null 2>&1
        return
    fi
    exec 6>"$state/last.log"
    exec > >(
        exec 7>&- 8>&- 9>&-
        head -c "$payload_limit" >&6 || true
        if [[ "$(stat -Lc '%s' /proc/self/fd/6 2>/dev/null || printf 0)" -ge "$payload_limit" ]]; then
            printf '\n[VSCode log limit reached. Additional output omitted.]\n' >&6 || true
        fi
        exec 6>&-
        exec cat >/dev/null
    ) 2>&1
    exec 6>&-
}

start_log
if [[ -e "$socket_path" || -L "$socket_path" || -e "$lock_path" || -L "$lock_path" ]]; then
    printf 'Display %s already has a socket or lock. Inspect its owner.\n' "$display" >&2
    exit 1
fi

server_pid=
title_pid=
ime_dir=
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
    rm -f -- "$state/editor.pid" "$state/editor.pid.tmp"
    if [[ -n "$dock_tag" ]]; then
        rm -f -- "$state/editor-token"
    fi
    if [[ -n "$title_pid" ]]; then
        kill "$title_pid" 2>/dev/null || true
        wait "$title_pid" 2>/dev/null || true
    fi
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
        "$prefix/bin/am" broadcast --user 0 -a com.termux.x11.ACTION_STOP -p "$android_package" \
            --es document_tag "$tag" >/dev/null 2>&1 || true
    fi
    if [[ -n "$ime_dir" ]]; then
        rm -f -- "$ime_dir/commit"
        rmdir -- "$ime_dir"
    fi
}

trap close_display EXIT
trap 'exit 130' HUP INT TERM
unset TERMUX_X11_XSTARTUP
unset TABLET_VSCODE_IME_SOCKET
unset TABLET_VSCODE_WINDOW_TOKEN
if [[ -n "$dock_tag" ]]; then
    export TABLET_VSCODE_WINDOW_TOKEN="$editor_token" TABLET_VSCODE_CLOSE_HELPER="$title_bridge"
    export TABLET_VSCODE_CLOSE_STATE="$state" TABLET_VSCODE_CLOSE_CONTAINER="$container" TABLET_VSCODE_CLOSE_USER="$user"
fi
guest_ime_socket=
if [[ @IME_BRIDGE@ == 1 ]]; then
    ime_dir=$(mktemp -d "$TMPDIR/vscode-ime.XXXXXX")
    export TABLET_VSCODE_IME_SOCKET="$ime_dir/commit"
    guest_ime_socket="/tmp/${ime_dir##*/}/commit"
fi
DISPLAY="$display" "${x11_command[@]}" "$display" -tag "$tag" -nolisten tcp "${x11_args[@]}" 7>&- 9>&- &
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
title=
if [[ -n "$dock_tag" ]]; then
    title_args=(initial "$display" "$tag" "$state" --workspace "$workspace")
    [[ "$fresh" != 1 ]] || title_args+=(--fresh)
    title=$("$prefix/bin/python" "$title_bridge" "${title_args[@]}") || title=
fi
show_window "$tag" "$title" "$editor_token"
if [[ -n "$dock_tag" ]]; then
    "$prefix/bin/python" "$title_bridge" watch "$display" "$tag" "$state" 7>&- 9>&- &
    title_pid=$!
fi

@GUEST_START@
set -euo pipefail
umask 077
@EDITOR_PID_HANDOFF@
root="$HOME/@PROFILE_DIR@"
export DISPLAY="$1" GDK_SCALE="$2" GDK_DPI_SCALE=1 XDG_SESSION_TYPE=x11
slot=$3
unset TABLET_VSCODE_DOCK_TAG TABLET_VSCODE_ANDROID_AM TABLET_VSCODE_WINDOW_TOKEN
if [[ -n "$4" ]]; then
    export TABLET_VSCODE_DOCK_TAG="$4" TABLET_VSCODE_ANDROID_AM=@PREFIX_SHELL@/bin/am
    export TABLET_VSCODE_WINDOW_TOKEN="$7"
fi
fresh=$5
workspace=$6
ime_socket=$8
shift 8
unset TABLET_VSCODE_IME_SOCKET
if [[ -n "$ime_socket" ]]; then
    export TABLET_VSCODE_IME_SOCKET="$ime_socket"
fi
export GDK_GL=disable NO_AT_BRIDGE=1
export XDG_CONFIG_HOME="$root/config" XDG_DATA_HOME="$root/data" XDG_CACHE_HOME="$root/cache" XDG_RUNTIME_DIR="$root/run"
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS DBUS_STARTER_ADDRESS DBUS_STARTER_BUS_TYPE
unset WAYLAND_DISPLAY GDK_CORE_DEVICE_EVENTS ELECTRON_RUN_AS_NODE VSCODE_IPC_HOOK_CLI BROWSER XDG_CURRENT_DESKTOP DESKTOP_SESSION
code_data="$root/code"
if [[ "$slot" != 0 ]]; then
    code_data="$root/windows/$slot/code"
    export XDG_RUNTIME_DIR="$root/run/$slot"
    mkdir -p "$code_data/User"
    for filename in settings.json keybindings.json; do
        source="$root/code/User/$filename"
        target="$code_data/User/$filename"
        if [[ -f "$source" && ! -e "$target" && ! -L "$target" ]]; then
            (set -o noclobber; cat "$source" >"$target")
        fi
    done
fi
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR" "$code_data/User" "$root/extensions"
settings="$code_data/User/settings.json"
if [[ ! -e "$settings" && ! -L "$settings" ]]; then
    (set -o noclobber; printf '%s\n' '{"window.newWindowDimensions":"maximized"}' >"$settings")
fi
export VSCODE_STANDALONE_HOME="$root"
export VSCODE_STANDALONE_DATA="$code_data"
export VSCODE_STANDALONE_WORKSPACE="$workspace"
if [[ "$fresh" == 1 ]]; then
    set -- "$@" --new-window --skip-welcome
fi

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
    if [[ -n "${TABLET_VSCODE_IME_SOCKET:-}" ]]; then
        export GTK_IM_MODULE=tablet-vscode GTK_IM_MODULE_FILE="$VSCODE_STANDALONE_HOME/ime/immodules.cache"
        set -- "$@" --gtk-version=3
    fi
@EDITOR_START@
@CODE_START@
SESSION
GUEST
