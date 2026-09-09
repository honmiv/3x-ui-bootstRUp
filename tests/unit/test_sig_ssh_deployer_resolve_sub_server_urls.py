#!/usr/bin/env python3
"""Signature test for ssh_deployer.resolve_sub_server_urls."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigResolveSubServerUrls(unittest.TestCase):
    def test_ssh_deployer_resolve_sub_server_urls_signature(self):
        sig = inspect.signature(ssh_deployer.resolve_sub_server_urls)
        self.assertEqual(list(sig.parameters.keys()), ["proxy_sub_url", "freedom_sub_url"])


if __name__ == "__main__":
    unittest.main()
