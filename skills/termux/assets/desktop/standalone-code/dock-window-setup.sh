mode="${1:-open}"
workspace="${2:-}"
launch_request="${3:-}"
if (( $# > 3 )) || [[ "$mode" != open && "$mode" != new && "$mode" != ack ]] ||
   [[ -n "$workspace" && ( "$mode" != new || "$workspace" != /* ) ]] ||
   [[ -n "$launch_request" && ! "$launch_request" =~ ^[0-9a-f]{32}$ ]] ||
   [[ "$mode" == ack && -z "$launch_request" ]]; then
    printf 'Usage: %s [open | new [ABSOLUTE_WORKSPACE_PATH]]\n' "$0" >&2
    exit 2
fi

dock_state="$state/dock"
if [[ "$mode" == ack ]]; then
    ticket="$dock_state/requests/$launch_request"
    [[ -d "$ticket" && -O "$ticket" && ! -L "$ticket" ]] || exit 1
    : >"$ticket/attached"
    exit
fi
mkdir -p "$dock_state"
exec 7>"$state/dock-settings.lock"
flock -s 7
exec 8>"$dock_state/dispatch.lock"
flock 8

if [[ "$mode" == open ]]; then
    for lease in "$dock_state/"*/session.lock; do
        [[ -f "$lease" ]] || continue
        window_state="${lease%/*}"
        slot="${window_state##*/}"
        [[ "$slot" =~ ^[0-9]{1,2}$ ]] || continue
        exec 9<"$lease"
        if ! flock -n 9; then
            if [[ -f "$window_state/editor-token" ]]; then
                read -r editor_token <"$window_state/editor-token"
            fi
            exec 7>&- 8>&- 9>&-
            show_window "vscode-$slot" "" "$editor_token"
            exit
        fi
        exec 9>&-
    done
fi

base_display="${display#:}"
for ((slot = 0; slot < 100; slot++)); do
    candidate=$(((base_display + slot) % 100))
    (( candidate != desktop_display )) || continue
    [[ ! -e "$TMPDIR/.X11-unix/X$candidate" && ! -L "$TMPDIR/.X11-unix/X$candidate" &&
       ! -e "$TMPDIR/.X$candidate-lock" && ! -L "$TMPDIR/.X$candidate-lock" ]] || continue
    state="$dock_state/$slot"
    mkdir -p "$state"
    exec 9>"$state/session.lock"
    if flock -n 9; then
        display=":$candidate"
        tag="vscode-$slot"
        dock_tag="$tag"
        [[ "$mode" != new ]] || fresh=1
        break
    fi
    exec 9>&-
done
exec 8>&-
if [[ -z "$dock_tag" ]]; then
    printf '%s\n' 'No separate X11 display is available for VS Code.' >&2
    exit 1
fi
editor_token="$launch_request"
if [[ -z "$editor_token" ]]; then
    editor_token=$("$prefix/bin/python" -c 'import secrets; print(secrets.token_hex(16))')
fi
token_file=$(mktemp "$state/.editor-token.XXXXXX")
printf '%s\n' "$editor_token" >"$token_file"
mv -fT -- "$token_file" "$state/editor-token"
