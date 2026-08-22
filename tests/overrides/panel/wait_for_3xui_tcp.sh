wait_for_3xui_tcp() {

    local port="$1"
    local target="tcp://127.0.0.1:${port}" timeout=60 counter=0
    while ! panel_exec bash -c "true >/dev/tcp/127.0.0.1/${port}" &>/dev/null; do
        if [[ "$counter" -ge "$timeout" ]]; then
            die "3x-ui did not respond at $target within $timeout seconds."
        fi
        sleep 1
        ((counter++))
    done
    success "3x-ui responded at $target in ${counter} sec."
}
