build_sub_and_connect_urls() {
    local client_name_enc raw_sub_data
    client_name_enc=$(url_encode "$CLIENT_EMAIL")
    CLIENT_SUBSCRIPTION_URL="https://${DOMAIN}/${XUI_SUB_PATH}/${client_name_enc}"
    info "$MSG_SUB_FETCHING"
    raw_sub_data=$(panel_exec curl -sL -H "User-Agent: go-http-client/1.1" "http://127.0.0.1:${XUI_SUB_PORT}/${XUI_SUB_PATH}/${client_name_enc}" | base64 -d 2>/dev/null)
    [[ -n "$raw_sub_data" ]] || die "$MSG_SUB_FETCH_ERR"
    CLIENT_VLESS_TCP_URL=$(echo "$raw_sub_data" | grep "type=tcp" || true)
    CLIENT_VLESS_XHTTP_URL=$(echo "$raw_sub_data" | grep "type=xhttp" || true)
    [[ -n "$CLIENT_VLESS_TCP_URL" || -n "$CLIENT_VLESS_XHTTP_URL" ]] || die "$MSG_SUB_EXTRACT_ERR"
    success "$MSG_SUB_FETCH_SUCCESS"
}
