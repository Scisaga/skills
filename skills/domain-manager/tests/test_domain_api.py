from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "domain_api.py"
SPEC = importlib.util.spec_from_file_location("domain_api", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
domain_api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = domain_api
SPEC.loader.exec_module(domain_api)


class DomainApiTests(unittest.TestCase):
    def test_dynadot_signature_matches_known_vector(self) -> None:
        signature = domain_api.create_dynadot_signature(
            "test-key",
            "test-secret",
            "/restful/v2/accounts/info?page=1",
            "550e8400-e29b-41d4-a716-446655440000",
            '{"a":1}',
        )
        self.assertEqual(signature, "xlEGxHrdSsmKqnGcvLdosQkA1bfBqzavQFKb8I4Uq1Y=")

    def test_provider_path_is_pinned(self) -> None:
        with self.assertRaises(ValueError):
            domain_api.validate_path("gandi", "/restful/v2/accounts/info")
        with self.assertRaises(ValueError):
            domain_api.validate_path("dynadot", "https://evil.example/restful/v2/x")
        with self.assertRaises(ValueError):
            domain_api.validate_path("gandi", "/v5/domain/../organization")

    def test_plan_id_changes_with_body(self) -> None:
        first = domain_api.build_request_spec(
            "gandi",
            "production",
            "PUT",
            "/v5/livedns/domains/example.com/records/www/A",
            (),
            {"rrset_values": ["192.0.2.1"]},
            '{"rrset_values":["192.0.2.1"]}',
        )
        second = domain_api.build_request_spec(
            "gandi",
            "production",
            "PUT",
            "/v5/livedns/domains/example.com/records/www/A",
            (),
            {"rrset_values": ["192.0.2.2"]},
            '{"rrset_values":["192.0.2.2"]}',
        )
        self.assertNotEqual(domain_api.plan_id(first), domain_api.plan_id(second))

    def test_redaction_preserves_status_code(self) -> None:
        value = {
            "code": 200,
            "access_token": "secret-token",
            "authinfo": "epp-secret",
            "nested": {"password": "secret-password"},
        }
        redacted = domain_api.redact_data(value)
        self.assertEqual(redacted["code"], 200)
        self.assertEqual(redacted["access_token"], "<redacted>")
        self.assertEqual(redacted["authinfo"], "<redacted>")
        self.assertEqual(redacted["nested"]["password"], "<redacted>")
        shown = domain_api.redact_data(value, show_sensitive=True)
        self.assertEqual(shown["authinfo"], "epp-secret")
        self.assertEqual(shown["access_token"], "<redacted>")

    def test_query_encoding_is_part_of_signature_path(self) -> None:
        spec = domain_api.build_request_spec(
            "dynadot",
            "sandbox",
            "GET",
            "/restful/v2/domains",
            (("page", "1"), ("filter", "a b")),
            None,
            "",
        )
        self.assertEqual(
            spec.path_and_query,
            "/restful/v2/domains?page=1&filter=a%20b",
        )

    def test_mutation_plan_never_executes_request(self) -> None:
        args = argparse.Namespace(
            provider="gandi",
            method="PUT",
            path="/v5/livedns/domains/example.com/records/www/A",
            query=[],
            body='{"rrset_values":["192.0.2.1"]}',
            body_file=None,
            sandbox=False,
            plan=False,
            apply=False,
            confirm=None,
            timeout=30.0,
            show_sensitive=False,
        )
        with mock.patch.object(domain_api, "execute_request") as execute:
            with contextlib.redirect_stdout(io.StringIO()):
                result = domain_api.run_request(args)
        self.assertEqual(result, 0)
        execute.assert_not_called()

    def test_valid_confirmation_reaches_executor(self) -> None:
        body_value, body_text = domain_api.parse_body('{"enabled":true}', None)
        spec = domain_api.build_request_spec(
            "gandi",
            "production",
            "PATCH",
            "/v5/domain/domains/example.com/autorenew",
            (),
            body_value,
            body_text,
        )
        args = argparse.Namespace(
            provider="gandi",
            method="PATCH",
            path=spec.path,
            query=[],
            body='{"enabled":true}',
            body_file=None,
            sandbox=False,
            plan=False,
            apply=True,
            confirm=domain_api.plan_id(spec),
            timeout=30.0,
            show_sensitive=False,
        )
        with mock.patch.object(domain_api, "execute_request", return_value=0) as execute:
            result = domain_api.run_request(args)
        self.assertEqual(result, 0)
        execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
