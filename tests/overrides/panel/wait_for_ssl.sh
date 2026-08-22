wait_for_ssl() {
    local cert_timeout=30 cert_counter=0
    section "Verifying local Caddy SSL certificate"

    while ! curl -sk --connect-timeout 2 --max-time 5 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}:443" -o /dev/null; do
        if [[ "$cert_counter" -ge "$cert_timeout" ]]; then
            die "Timed out waiting for local Caddy HTTPS on port 443"
        fi
        sleep 1
        ((cert_counter++))
    done

    local issuer
    issuer=$(echo | openssl s_client -connect 127.0.0.1:443 -servername "${DOMAIN}" 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null || true)
    if [[ "$issuer" =~ "Caddy Local Authority" ]]; then
        success "Verified local Caddy self-signed certificate on port 443: ${issuer}"
    else
        success "Local Caddy HTTPS is responding on port 443."
    fi
}
