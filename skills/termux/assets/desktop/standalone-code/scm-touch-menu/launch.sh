# Sourced by the standalone VS Code session.
tablet_code_with_scm_touch_menu() {
    local worker=$1 code_pid worker_pid input_fd output_fd status=0
    shift
    coproc TABLET_CODE {
        exec "$@" --remote-debugging-pipe 3<&0 4>&1 </dev/null >&2
    }
    code_pid=$TABLET_CODE_PID
    # Electron exits if the client disconnects. Keep both pipes until Code closes.
    exec {output_fd}<&"${TABLET_CODE[0]}" {input_fd}>&"${TABLET_CODE[1]}"
    /usr/bin/python3 -B "$worker" <&"$output_fd" >&"$input_fd" &
    worker_pid=$!

    wait "$code_pid" || status=$?
    exec {output_fd}<&- {input_fd}>&-
    kill "$worker_pid" 2>/dev/null || true
    wait "$worker_pid" 2>/dev/null || true
    return "$status"
}
