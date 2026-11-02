import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "scripts/services/ddns"
SPEC = importlib.util.spec_from_file_location("ddns_address", SERVICE / "ddns_address.py")
ADDRESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADDRESS)
API_SPEC = importlib.util.spec_from_file_location("aliyun_api", SERVICE / "aliyun_api.py")
API = importlib.util.module_from_spec(API_SPEC)
API_SPEC.loader.exec_module(API)
PUBLIC = "2606:4700:4700::1111"


def interface(*addresses):
    return [{"flags": ["UP", "LOWER_UP"], "addr_info": list(addresses)}]


def address(value=PUBLIC, **extra):
    return {"family": "inet6", "scope": "global", "local": value, **extra}


class AddressTests(unittest.TestCase):
    def test_selects_stable_global_ipv6(self):
        values = interface(address("fe80::1"), address("fd00::1"), address(),
                           address("2606:4700:4700::1001", temporary=True))
        self.assertEqual(ADDRESS.select_address(values, "AAAA"), PUBLIC)

    def test_invalid_or_unsafe_addresses_are_rejected(self):
        for value in ["192.168.1.7", "127.0.0.1", "0.0.0.0", "not-an-ip", "224.0.0.1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ADDRESS.public_address(value, "A")

    def test_inactive_ipv6_states_are_rejected(self):
        for flags in [{"tentative": True}, {"dadfailed": True}, {"deprecated": True},
                      {"temporary": True}, {"preferred_life_time": 0},
                      {"valid_life_time": 0}, {"flags": ["temporary"]}]:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                ADDRESS.select_address(interface(address(**flags)), "AAAA")

    def test_down_interface_is_rejected(self):
        values = interface(address())
        values[0]["flags"] = []
        with self.assertRaises(ValueError):
            ADDRESS.select_address(values, "AAAA")

    def test_multiple_stable_prefixes_are_rejected(self):
        with self.assertRaises(ValueError):
            ADDRESS.select_address(interface(address(), address("2606:4700:4700::1001")), "AAAA")

    def test_canonical_ip_comparison(self):
        self.assertEqual(ADDRESS.public_address("2606:4700:4700:0:0:0:0:1111", "AAAA"), PUBLIC)

    def test_direct_dns_keeps_hostname_for_tls(self):
        answer = "cdn.example.net.\n8.8.8.8\n1.1.1.1\n8.8.8.8\n"
        self.assertEqual(ADDRESS.lookup_resolve_entry("https://lookup.example/ip", "A", answer),
                         "lookup.example:443:8.8.8.8,1.1.1.1")

    def test_direct_dns_ipv6_brackets_and_no_private_destination(self):
        self.assertEqual(ADDRESS.lookup_resolve_entry("https://lookup.example:8443/ip", "AAAA", PUBLIC),
                         f"lookup.example:8443:[{PUBLIC}]")
        with self.assertRaises(ValueError):
            ADDRESS.lookup_resolve_entry("https://lookup.example/ip", "A", "192.168.1.1\ncdn.example.net.")


class ApiTests(unittest.TestCase):
    def test_signature_matches_official_v3_vector(self):
        # https://www.alibabacloud.com/help/en/sdk/product-overview/v3-request-structure-and-signature
        params = {"ImageId": "win2019_1809_x64_dtc_zh-cn_40G_alibase_20230811.vhd", "RegionId": "cn-shanghai"}
        _, headers = API.signed_headers("POST", "ecs.cn-shanghai.aliyuncs.com", "RunInstances", "2014-05-26",
                                       params, "YourAccessKeyId", "YourAccessKeySecret", "2023-10-26T10:22:32Z",
                                       "3156853299f313e23d1673dc12e1703d")
        self.assertTrue(headers["Authorization"].endswith("Signature=06563a9e1b43f5dfe96b81484da74bceab24a1d853912eee15083a6f0f3283c0"))

    def test_pinned_https_endpoint_and_encoded_ipv6(self):
        observed = []

        class FakeOpener:
            def open(self, req, timeout):
                observed.append((req, timeout))
                return io.BytesIO(b'{"RecordId":"test-record"}')

        result = API.request("AddDomainRecord", {"RR": "@", "Value": PUBLIC}, "fake-id", "fake-secret", 10, FakeOpener())
        req, timeout = observed[0]
        self.assertEqual(result["RecordId"], "test-record")
        self.assertTrue(req.full_url.startswith("https://alidns.aliyuncs.com/"))
        self.assertIn("RR=%40", req.full_url)
        self.assertIn("Value=2606%3A4700%3A4700%3A%3A1111", req.full_url)
        self.assertNotIn("fake-id", req.full_url)
        self.assertNotIn("fake-secret", req.full_url)
        self.assertEqual(timeout, 10)

    def test_redirects_are_rejected(self):
        self.assertIsNone(API.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.invalid"))


MOCK_CLI = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
assert os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'] == 'fake-test-key-id'
assert os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'] == 'fake-test-key-secret'
assert os.environ['ALIBABA_CLOUD_IGNORE_PROFILE'] == 'TRUE'
assert '--profile' not in sys.argv
if os.environ.get('MOCK_API_FAIL'):
    print(os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'] + ' ' + os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'], file=sys.stderr)
    sys.exit(2)
state_path = Path(os.environ['MOCK_STATE'])
state = json.loads(state_path.read_text())
action_index = sys.argv.index('alidns') + 1
action = sys.argv[action_index]
params = dict(zip(sys.argv[action_index + 1::2], sys.argv[action_index + 2::2]))
if action == 'DescribeDomainRecords':
    print(json.dumps({'TotalCount': len(state['records']), 'DomainRecords': {'Record': state['records']}}))
elif action == 'DescribeDomainRecordInfo':
    record = next(r for r in state['records'] if r['RecordId'] == params['--RecordId'])
    if os.environ.get('MOCK_BAD_READBACK'):
        record['Value'] = '2606:4700:4700::9999'
    print(json.dumps(record))
elif action in ['AddDomainRecord', 'UpdateDomainRecord']:
    state['writes'].append({'action': action, 'params': params})
    record = {'RecordId': params.get('--RecordId', 'new-id'), 'RR': params['--RR'],
              'Type': params['--Type'], 'Value': params['--Value'],
              'TTL': int(params['--TTL']), 'Line': params['--Line'], 'Status': 'ENABLE'}
    state['records'] = [r for r in state['records'] if r['RecordId'] != record['RecordId']] + [record]
    state_path.write_text(json.dumps(state))
    print(json.dumps({'RecordId': record['RecordId']}))
else:
    raise SystemExit('unexpected API action: ' + action)
'''


@unittest.skipIf(os.name == "nt", "run Bash integration tests under Linux/WSL")
class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ["scripts/shared/lib/common.sh", "scripts/run.sh",
                         "scripts/services/ddns/aliyun_ddns.sh", "scripts/services/ddns/ddns_address.py"]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, content in {
            "aliyun": MOCK_CLI,
            "ip": "#!/usr/bin/env python3\nimport os\nprint(os.environ['MOCK_IP_JSON'])\n",
            "curl": "#!/bin/sh\necho unexpected-external-ip-lookup >&2\nexit 9\n",
        }.items():
            target = self.bin / name
            target.write_text(content)
            target.chmod(0o755)
        self.state_path = self.root / "state.json"
        self.save_records([])
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        DDNS_TARGETS="example.com|AAAA|home", DDNS_INTERFACE="eth0",
                        DDNS_IPV4_SOURCE="auto", DDNS_LOOKUP_DNS_SERVER="",
                        DDNS_API_BACKEND="cli",
                        ALIYUN_ACCESS_KEY_ID="fake-test-key-id", ALIYUN_ACCESS_KEY_SECRET="fake-test-key-secret",
                        MOCK_STATE=str(self.state_path), MOCK_IP_JSON=json.dumps(interface(address())))

    def save_records(self, records):
        self.state_path.write_text(json.dumps({"records": records, "writes": []}))

    def state(self):
        return json.loads(self.state_path.read_text())

    def record(self, **extra):
        return {"RecordId": "existing-id", "RR": "home", "Type": "AAAA", "Value": PUBLIC,
                "Line": "default", "TTL": 1200, "Status": "ENABLE", **extra}

    def run_script(self, *args):
        return subprocess.run(["bash", str(self.root / "scripts/run.sh"), "service", "ddns",
                               "aliyun_ddns.sh", *args], check=False, env=self.env, capture_output=True, text=True, timeout=15)

    def configure_nat_lookup(self, value="8.8.4.4", exit_status=0):
        self.env.update(DDNS_TARGETS="example.com|A|home;example.com|AAAA|home", DDNS_IPV4_SOURCE="public",
                        DDNS_IPV4_LOOKUP_URL="https://lookup.example/ip", DDNS_LOOKUP_DNS_SERVER="192.0.2.53",
                        MOCK_CURL_ARGS=str(self.root / "curl-args.json"))
        self.env["MOCK_IP_JSON"] = json.dumps(interface(
            {"family": "inet", "scope": "global", "local": "192.168.1.7"}, address()))
        (self.bin / "dig").write_text("#!/usr/bin/env python3\nimport sys\n"
                                     "assert '@192.0.2.53' in sys.argv and 'lookup.example' in sys.argv\n"
                                     "print('cdn.example.net.\\n8.8.8.8')\n")
        (self.bin / "dig").chmod(0o755)
        (self.bin / "curl").write_text("#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\n"
                                      "Path(os.environ['MOCK_CURL_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
                                      f"print({value!r})\nsys.exit({exit_status})\n")

    def test_nat_ipv4_is_direct_and_keeps_interface_ipv6(self):
        self.configure_nat_lookup()
        old_a = self.record(RecordId="ipv4-id", Type="A", Value="1.1.1.1")
        old_aaaa = self.record()
        self.save_records([old_a, old_aaaa])
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.state()
        self.assertEqual(len(state["writes"]), 1)
        self.assertEqual(state["writes"][0]["params"]["--Type"], "A")
        self.assertEqual(state["writes"][0]["params"]["--Value"], "8.8.4.4")
        self.assertIn(old_aaaa, state["records"])
        args = json.loads((self.root / "curl-args.json").read_text())
        self.assertEqual(args[0], "-q")
        for flag, expected in [("--noproxy", "*"), ("--proxy", ""), ("--interface", "eth0"),
                               ("--resolve", "lookup.example:443:8.8.8.8")]:
            self.assertEqual(args[args.index(flag) + 1], expected)
        self.assertIn("-4", args)

    def test_nat_lookup_failure_does_not_write_or_use_proxy(self):
        for value, exit_status in [("192.168.1.7", 0), ("8.8.4.4", 7)]:
            with self.subTest(value=value, exit_status=exit_status):
                self.configure_nat_lookup(value, exit_status)
                records = [self.record()]
                self.save_records(records)
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.state()["writes"], [])
                self.assertEqual(self.state()["records"], records)

    def test_create_then_idempotent_without_touching_a_record(self):
        old_a = self.record(RecordId="ipv4-id", Type="A", Value="8.8.8.8")
        self.save_records([old_a])
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(old_a, self.state()["records"])
        self.assertEqual(len(self.state()["writes"]), 1)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skip home.example.com", result.stdout)
        self.assertEqual(len(self.state()["writes"]), 1)

    def test_native_backend_does_not_require_cli(self):
        self.env["DDNS_API_BACKEND"] = "auto"
        (self.bin / "aliyun").unlink()
        native_mock = self.root / "scripts/services/ddns/aliyun_api.py"
        native_mock.write_text("import sys\nsys.argv.insert(1, 'alidns')\n" + MOCK_CLI)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no CLI or SDK dependency", result.stdout)
        self.assertEqual(len(self.state()["writes"]), 1)

    def test_update_preserves_ttl(self):
        self.save_records([self.record(Value="2606:4700:4700::1001")])
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["writes"][0]["params"]["--TTL"], "1200")

    def test_dry_run_never_writes(self):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["writes"], [])

    def test_no_public_address_does_not_write(self):
        self.env["MOCK_IP_JSON"] = json.dumps(interface(address("fd00::1")))
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["writes"], [])

    def test_duplicate_or_disabled_records_do_not_write(self):
        for records in [[self.record(), self.record(RecordId="second-id")], [self.record(Status="DISABLE")]]:
            with self.subTest(records=records):
                self.save_records(records)
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.state()["writes"], [])

    def test_errors_are_redacted_and_do_not_write(self):
        self.env["MOCK_API_FAIL"] = "1"
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("fake-test-key-id", result.stdout + result.stderr)
        self.assertNotIn("fake-test-key-secret", result.stdout + result.stderr)
        self.assertIn("[REDACTED]", result.stderr)
        self.assertNotIn("JSONDecodeError", result.stderr)
        self.assertEqual(self.state()["writes"], [])

    def test_failed_readback_is_not_reported_as_success(self):
        self.env["MOCK_BAD_READBACK"] = "1"
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("DDNS sync completed", result.stdout)


if __name__ == "__main__":
    unittest.main()
