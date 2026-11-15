#!/usr/bin/env python3
"""Deploy only the separate-UID manager APK; never reinstall shared-UID Termux plugins."""
import argparse
import json
import subprocess
from pathlib import Path


def call(args, script=None):
    p = subprocess.run([str(x) for x in args], input=script, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=90)
    if p.returncode: raise RuntimeError(f"{Path(args[0]).name} failed: {(p.stderr or p.stdout)[-1400:]}")
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--ssh-target", required=True, help="Existing trusted user@device-IP")
    parser.add_argument("--ssh-port", type=int, default=8022)
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--ssh-bind", help="Optional source IP for overlapping VPN routes")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apk.is_file(): parser.error("APK not found; run build-manager first")
    if args.ssh_target.startswith("-") or not 1 <= args.ssh_port <= 65535: parser.error("Invalid SSH target/port")
    if not args.apply:
        print(json.dumps({"apk": str(args.apk), "package": "com.scisaga.tabletdesktop", "changes_device": False, "permissions": ["com.termux.permission.RUN_COMMAND"], "termux_property": "allow-external-apps=true"}))
        return
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-p", str(args.ssh_port)]
    if args.identity: ssh += ["-i", str(args.identity)]
    if args.ssh_bind: ssh += ["-b", args.ssh_bind]
    ssh += [args.ssh_target, "/data/data/com.termux/files/usr/bin/bash -s"]
    call(ssh, "export PATH=/data/data/com.termux/files/usr/bin:$PATH\ncommand -v desktop >/dev/null\n")
    adb = [args.adb, "-s", args.serial]
    call(adb + ["install", "-r", str(args.apk.resolve())])
    call(adb + ["shell", "pm", "grant", "com.scisaga.tabletdesktop", "com.termux.permission.RUN_COMMAND"])
    script = '''export PATH=/data/data/com.termux/files/usr/bin:$PATH
python - <<'PY'
from pathlib import Path
import re,shutil,time
p=Path.home()/'.termux/termux.properties'
old=p.read_text(encoding="utf-8") if p.exists() else ''
if p.exists(): shutil.copy2(p,p.with_name('termux.properties.before-manager-'+str(int(time.time()))))
line='allow-external-apps = true'
new=re.sub(r'(?m)^\\s*allow-external-apps\\s*=.*$',line,old) if re.search(r'(?m)^\\s*allow-external-apps\\s*=',old) else old.rstrip()+'\\n'+line+'\\n'
p.parent.mkdir(parents=True,exist_ok=True);p.write_text(new);p.chmod(0o600)
PY
termux-reload-settings
'''
    call(ssh, script)
    activities = call(adb + ["shell", "cmd", "package", "query-activities", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", "com.scisaga.tabletdesktop"])
    if ".DesktopEntry" not in activities or ".ManagerActivity" not in activities: raise RuntimeError("Expected both launcher entries; inspect package before using it")
    print("Installed manager with Linux desktop and management entries. Keep the signing key for future in-place updates. Open each entry once and handle any manufacturer launch prompt.")


if __name__ == "__main__":
    try: main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc: raise SystemExit(str(exc))
