#!/usr/bin/env python3
"""Select and validate public addresses without depending on a lookup service."""

import argparse
import ipaddress
import json
import sys
from urllib.parse import urlsplit


def public_address(value, record_type):
    address = ipaddress.ip_address(value.strip())
    version = {"A": 4, "AAAA": 6}[record_type]
    if address.version != version or not address.is_global or address.is_multicast:
        raise ValueError(f"expected a public {record_type} address, got {value!r}")
    return str(address)


def select_address(interfaces, record_type):
    family = {"A": "inet", "AAAA": "inet6"}[record_type]
    candidates = []
    for interface in interfaces:
        if "UP" not in interface.get("flags", []):
            continue
        for item in interface.get("addr_info", []):
            flags = set(item.get("flags", []))
            if item.get("family") != family or item.get("scope") != "global":
                continue
            if any(item.get(flag) or flag in flags for flag in
                   ("temporary", "deprecated", "tentative", "dadfailed")):
                continue
            if item.get("valid_life_time") == 0 or item.get("preferred_life_time") == 0:
                continue
            try:
                candidates.append(public_address(item.get("local", ""), record_type))
            except ValueError:
                continue
    if not candidates:
        raise ValueError(f"interface has no active, stable public {record_type} address")
    # A multi-prefix transition is ambiguous. Wait for one stable address rather
    # than publishing whichever order the kernel happened to return.
    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        raise ValueError(f"interface has {len(candidates)} stable public {record_type} addresses; select a more specific interface")
    return candidates[0]


def lookup_resolve_entry(url, record_type, answer):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("IP lookup URL must use HTTP(S) and include a hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = []
    for line in answer.splitlines():
        try:
            value = public_address(line.strip(), record_type)
        except ValueError:
            continue
        if value not in addresses:
            addresses.append(value)
    if not addresses:
        raise ValueError(f"direct DNS returned no public {record_type} address for {parsed.hostname}")
    values = [f"[{value}]" if record_type == "AAAA" else value for value in addresses]
    # Keep the hostname in the URL and TLS SNI; --resolve only replaces DNS.
    return f"{parsed.hostname}:{port}:{','.join(values)}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["interface", "validate", "resolve"])
    parser.add_argument("record_type", choices=["A", "AAAA"])
    parser.add_argument("--url", help="IP lookup URL for resolve mode")
    args = parser.parse_args()
    try:
        if args.mode == "interface":
            value = select_address(json.load(sys.stdin), args.record_type)
        elif args.mode == "resolve":
            value = lookup_resolve_entry(args.url or "", args.record_type, sys.stdin.read())
        else:
            value = public_address(sys.stdin.read().strip(), args.record_type)
        print(value)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"DDNS address error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
