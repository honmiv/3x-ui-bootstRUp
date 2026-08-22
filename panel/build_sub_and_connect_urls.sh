build_sub_and_connect_urls() {
    local client_name_enc
    client_name_enc=$(url_encode "$CLIENT_EMAIL")

    CLIENT_SUBSCRIPTION_URL="https://${DOMAIN}/${XUI_SUB_PATH}/${client_name_enc}"

    info "$MSG_SUB_FETCHING"

    local raw_sub_data
    raw_sub_data=$(curl -sL -k -H "User-Agent: go-http-client/1.1" "$CLIENT_SUBSCRIPTION_URL" | base64 -d 2>/dev/null)

    if [[ -z "$raw_sub_data" ]]; then
        die "$MSG_SUB_FETCH_ERR"
    fi

    CLIENT_VLESS_TCP_URL=$(echo "$raw_sub_data" | grep "type=tcp" || true)
    CLIENT_VLESS_XHTTP_URL=$(echo "$raw_sub_data" | grep "type=xhttp" || true)

    if [[ -z "$CLIENT_VLESS_TCP_URL" && -z "$CLIENT_VLESS_XHTTP_URL" ]]; then
        die "$MSG_SUB_EXTRACT_ERR"
    fi

    success "$MSG_SUB_FETCH_SUCCESS"
}
