wait_for_3xui_tcp() {
    local port="$1"
    local target="tcp://127.0.0.1:${port}"
    wait_for_3xui_ready "$target" panel_exec bash -c "true >/dev/tcp/127.0.0.1/${port}"
}
