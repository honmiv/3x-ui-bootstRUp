process_templates() {
    section "Generating configuration"
    generate_config "./common/templates" "./working"
    generate_config "./sub-server/templates" "./working"
}
