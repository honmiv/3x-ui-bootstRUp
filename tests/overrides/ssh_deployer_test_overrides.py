"""
Test-only overrides for ssh_deployer.py backend URL resolvers.

DinD networking: subs-server inside DinD cannot reach host.docker.internal:8082
(inner docker0 ≠ real host).  This module monkey-patches resolve_sub_server_urls
so it returns reachable outer-Docker IPs + extra_hosts env vars.

Usage (at top of test, before run_deployment):

    from tests.overrides.ssh_deployer_test_overrides import install_dind_overrides
    install_dind_overrides(proxy_container, freedom_container)
"""

import ssh_deployer


def _make_dind_override(proxy_container: str, freedom_container: str):
    """Return a patched resolve_sub_server_urls closure for DinD."""
    from tests.helpers import get_outer_docker_ip
    from urllib.parse import urlparse

    def patched(russian_sub_url, freedom_sub_url):
        proxy_ip = get_outer_docker_ip(proxy_container) if proxy_container else ""
        freedom_ip = get_outer_docker_ip(freedom_container) if freedom_container else ""
        # Extract sub-paths from the production URLs and re-host on outer Docker IPs.
        if russian_sub_url:
            ru_path = urlparse(russian_sub_url).path.strip('/')
            russian_url = f"http://proxy-docker:80/{ru_path}"
        else:
            russian_url = ""
        if freedom_sub_url:
            fr_path = urlparse(freedom_sub_url).path.strip('/')
            freedom_url = f"http://freedom-docker:80/{fr_path}"
        else:
            freedom_url = ""
        extra_env = {}
        if proxy_ip:
            extra_env["TEST_PROXY_DOCKER_IP"] = proxy_ip
        if freedom_ip:
            extra_env["TEST_FREEDOM_DOCKER_IP"] = freedom_ip
        return russian_url, freedom_url, extra_env

    return patched


def install_dind_overrides(proxy_container: str, freedom_container: str):
    """Monkey-patch ssh_deployer.resolve_sub_server_urls for DinD test networking."""
    ssh_deployer.resolve_sub_server_urls = _make_dind_override(proxy_container, freedom_container)
