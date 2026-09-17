#!/usr/bin/env python3
"""Unit test ensuring all fields in MODES_SCHEMA exist in index.html or templates."""

import os
import re
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import MODES_SCHEMA


class TestAllSchemaFieldsExist(unittest.TestCase):
    def test_all_schema_fields_exist_in_html_or_templates(self):
        html_path = os.path.join(REPO_ROOT, "panel", "static", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        static_ids = set(re.findall(r'id=["\']([a-zA-Z0-9_-]+)["\']', html_content))

        ssh_prefixes = set(re.findall(r'data-ssh-prefix=["\']([a-zA-Z0-9_-]+)["\']', html_content))
        dynamic_ssh_ids = set()
        for prefix in ssh_prefixes:
            dynamic_ssh_ids.add(f"{prefix}_host")
            dynamic_ssh_ids.add(f"{prefix}_port")
            dynamic_ssh_ids.add(f"{prefix}_user")
            dynamic_ssh_ids.add(f"{prefix}_password")
            dynamic_ssh_ids.add(f"{prefix}_key")
            auth_base = prefix[:-4] if prefix.endswith("_vps") else prefix
            dynamic_ssh_ids.add(f"{auth_base}_auth_type")

        all_available_dom_ids = static_ids | dynamic_ssh_ids

        for idx, rule in enumerate(MODES_SCHEMA):
            fields_to_check = []
            if rule.get("kind") == "field":
                fields_to_check.append(rule["id"])
            elif rule.get("kind") == "group":
                fields_to_check.extend(rule.get("fields", []))

            auth_field = rule.get("authField")
            if auth_field:
                fields_to_check.append(auth_field)

            for fid in fields_to_check:
                self.assertIn(
                    fid,
                    all_available_dom_ids,
                    f"Field '{fid}' from MODES_SCHEMA rule #{idx} does not exist in index.html or SSH template",
                )


if __name__ == "__main__":
    unittest.main()
