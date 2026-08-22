wait_for_ssl() {
    local cert_timeout=300 cert_counter=0
    section "$MSG_WAIT_SSL"

    while ! curl -s --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            warn "$MSG_SSL_LOGS_HINT"
            die "$(printf "$MSG_SSL_TIMEOUT" "$cert_timeout")"
        fi
        printf "\r${YELLOW}${MSG_SSL_VALIDATING}${NC}" "$(show_spinner "$cert_counter")" "$cert_counter" "$cert_timeout"
        sleep 1
        ((cert_counter++))
    done

    printf "\r\033[K"
    success "$(printf "$MSG_SSL_SUCCESS" "$cert_counter")"
    echo
}
