process_templates() {
    section "$MSG_PROCESSING"
    generate_config "./common/templates" "./working"
    generate_config "./panel/templates" "./working"
}
