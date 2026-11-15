#!/usr/bin/env python3
"""Diagnose VPN/proxy/DNS separately, with no subscription/profile credential reads."""
import argparse
import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", help="Host mode: adb path")
    parser.add_argument("--serial")
    parser.add_argument("--check-network", action="store_true", help="Native mode: make bounded HTTPS probes to Google and Baidu")
    args = parser.parse_args()
    def run(command):
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    if args.adb:
        if not args.serial: parser.error("Host mode requires --serial")
        adb = [args.adb, "-s", args.serial, "shell"]
        vpn = run(adb + ["dumpsys", "vpn_management"])
        process = run(adb + ["pidof", "com.v2ray.ang"])
        print(json.dumps({"vpn": [x.strip() for x in vpn.stdout.splitlines() if "Active package name:" in x or "Active vpn type:" in x],
                          "vpn_query_available": vpn.returncode == 0, "v2ray_main_process_running": process.returncode == 0,
                          "note": "A proxy-only service may run in another process. Confirm local listeners and transport mode; a main process alone does not prove a working VPN."}, ensure_ascii=False, indent=2))
        return
    ports = []
    for port in (10808, 10809, 7890, 7891):
        try:
            with socket.create_connection(("127.0.0.1", port), .4): ports.append(port)
        except OSError: pass
    dns = Path("/etc/resolv.conf")
    resolvers = [x.split()[1] for x in dns.read_text(encoding="utf-8").splitlines() if x.startswith("nameserver ")] if dns.exists() else []
    result = {"open_candidate_loopback_ports": ports, "proxy_environment_present": [k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "all_proxy")],
              "resolvers_in_current_environment": resolvers, "uid": os.getuid() if hasattr(os, "getuid") else None,
              "note": "PRoot applications keep Termux's real Android UID. Include Termux in per-app VPN routing. Open ports do not prove a healthy upstream; compare native and guest tests."}
    if args.check_network:
        result["direct_https"] = {}
        for host in ("www.google.com", "www.baidu.com"):
            p = run(["curl", "--noproxy", "*", "--connect-timeout", "4", "--max-time", "8", "-sS", "-o", os.devnull, "-w", "%{http_code}", "https://" + host])
            result["direct_https"][host] = {"exit": p.returncode, "http": p.stdout.strip()}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc: raise SystemExit(str(exc))
