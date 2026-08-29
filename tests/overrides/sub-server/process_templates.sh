process_templates() {
    section "Generating configuration"
    generate_config "./common/templates" "./working"
    generate_config "./sub-server/templates" "./working"

    # Inject extra_hosts so subs-server (inside DinD) can reach sibling test VPS
    # containers by name instead of host.docker.internal (which resolves to inner
    # docker0, not the real host).
    local extra_entries=""
    [[ -n "${TEST_PROXY_DOCKER_IP:-}" ]]  && extra_entries+="      - \"proxy-docker:${TEST_PROXY_DOCKER_IP}\"\n"
    [[ -n "${TEST_FREEDOM_DOCKER_IP:-}" ]] && extra_entries+="      - \"freedom-docker:${TEST_FREEDOM_DOCKER_IP}\"\n"
    extra_entries+="      - \"host.docker.internal:host-gateway\"\n"

    sed -i "/    container_name: subs-server/a\\    extra_hosts:\n${extra_entries}" \
        ./working/docker-compose/docker-compose.yml
}
