wait_for_ssl() {
    local cert_timeout=300 cert_counter=0
    section "Waiting for SSL certificate"

    while ! curl -s --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            warn "Check logs: docker compose -f $DOCKER_COMPOSE_FILE logs caddy"
            die "SSL certificate was not obtained within $cert_timeout seconds."
        fi
        printf "\r${YELLOW}[..]${NC} Validating SSL certificate %s %s/%s" "$(show_spinner "$cert_counter")" "$cert_counter" "$cert_timeout"
        sleep 1
        ((cert_counter++))
    done
    echo
    success "SSL certificate is active."
}
