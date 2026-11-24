"""Check, download, or install a signed Microsoft Code package in Debian."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY = "https://packages.microsoft.com/repos/code"
KEY_URL = "https://packages.microsoft.com/keys/microsoft.asc"
KEY_FINGERPRINT = "BC528686B50D79E339D3721CEB3E94ADBE1229CF"
DEFAULT_KEY = Path("/usr/share/keyrings/microsoft.gpg")
SOURCE_DIR = Path("/etc/apt/sources.list.d")
PACKAGE_VERSION = re.compile(r"[0-9][0-9A-Za-z.+:~\-]{0,99}")


def run(args, *, timeout=30, check=True):
    result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
    if check and result.returncode:
        detail = (result.stdout + "\n" + result.stderr).strip()
        raise RuntimeError(f"{args[0]} exited {result.returncode}:\n{detail[-2500:]}")
    return result


def configured_source(directory):
    for name in ("vscode.sources", "vscode.list"):
        source = directory / name
        if not source.is_file():
            continue
        data = "\n".join(line for line in source.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("#")).strip()
        if not data:
            continue
        if source.suffix == ".sources":
            fields = {key.lower(): value.strip() for key, value in
                      re.findall(r"^([A-Za-z-]+):([^\n]*)$", data, re.M)}
            if len(fields) != len(data.splitlines()):
                raise ValueError(f"Review the Microsoft stable Code source in {source}")
            if fields.get("enabled", "yes").lower() == "no":
                continue
            allowed = {"types", "uris", "suites", "components", "architectures", "signed-by", "enabled"}
            if (fields.keys() - allowed or fields.get("types") != "deb"
                    or fields.get("uris", "").rstrip("/") != REPOSITORY
                    or fields.get("suites") != "stable" or fields.get("components") != "main"):
                raise ValueError(f"Review the Microsoft stable Code source in {source}")
            signed_by = fields.get("signed-by", "")
        else:
            data = "\n".join(line.partition("#")[0].rstrip() for line in data.splitlines()).strip()
            match = re.fullmatch(r"deb\s+\[([^\]]+)\]\s+" + re.escape(REPOSITORY) + r"/?\s+stable\s+main", data)
            if not match or "\n" in data:
                raise ValueError(f"Review the Microsoft stable Code source in {source}")
            parts = match[1].split()
            options = dict(option.split("=", 1) for option in parts if "=" in option)
            if len(options) != len(parts) or options.keys() - {"arch", "signed-by"} or not all(options.values()):
                raise ValueError(f"Review the signature options in {source}")
            signed_by = options.get("signed-by", "")
        if not re.fullmatch(r"/(?:etc/apt/keyrings|usr/share/keyrings)/[A-Za-z0-9_.-]+\.(?:gpg|asc)", signed_by):
            raise ValueError(f"Set a source-specific Signed-By keyring in {source}; see the official Linux setup guide")
        return source, Path(signed_by)
    raise ValueError("Microsoft VS Code APT source is missing; see the official Linux setup guide")


def key_needs_repair(key):
    return not key.is_file() or key.stat().st_size == 0


def repair_empty_key(key):
    if key != DEFAULT_KEY or key.is_symlink() or (key.exists() and not key.is_file()):
        raise ValueError(f"Review the missing or empty Signed-By keyring: {key}")
    if not key_needs_repair(key):
        return False
    if any(shutil.which(program) is None for program in ("curl", "gpg")):
        raise ValueError("Install Debian prerequisites with apt-get install ca-certificates curl gnupg")
    with tempfile.TemporaryDirectory(prefix=".vscode-key-", dir=key.parent) as directory:
        armor = Path(directory) / "microsoft.asc"
        binary = armor.with_suffix(".gpg")
        run(["curl", "--disable", "--proto", "=https", "--proto-redir", "=https", "--tlsv1.2", "-fsSL", "--retry", "2",
             "--max-time", "30", "-o", str(armor), KEY_URL], timeout=110)
        gpg = ["gpg", "--batch", "--homedir", directory]
        records = run(gpg + ["--with-colons", "--show-keys", str(armor)]).stdout.splitlines()
        primary = [records[index + 1].split(":")[9] for index, line in enumerate(records[:-1])
                   if line.startswith("pub:") and records[index + 1].startswith("fpr:")]
        if sum(line.startswith("pub:") for line in records) != 1 or primary != [KEY_FINGERPRINT]:
            raise ValueError("Microsoft repository key fingerprint mismatch")
        run(gpg + ["--dearmor", "--output", str(binary), str(armor)])
        if key.is_symlink() or not key_needs_repair(key):
            raise ValueError(f"Keyring changed while verifying the Microsoft public key: {key}")
        binary.chmod(0o644)
        binary.replace(key)
    return True


def package_status():
    output = run(["dpkg-query", "-W", "-f=${db:Status-Status}\t${Version}\t${Architecture}", "code"]).stdout
    status, version, architecture = output.split("\t")
    if status != "installed":
        raise ValueError("The Code package is not fully installed; check dpkg --audit in the guest")
    return version, architecture


def update_package(mode, requested, profile_version):
    if requested and not PACKAGE_VERSION.fullmatch(requested):
        raise ValueError("Use an exact Debian Code package version")
    installed, architecture = package_status()
    source, key = configured_source(SOURCE_DIR)
    scope = ["-o", f"Dir::Etc::sourcelist={source}", "-o", "Dir::Etc::sourceparts=-"]
    apt = ["apt-get", *scope, "-o", "Acquire::Retries=2", "-o", "Acquire::https::Timeout=20",
           "-o", "Acquire::AllowInsecureRepositories=false", "-o", "Acquire::AllowDowngradeToInsecureRepositories=false",
           "-o", "APT::Get::AllowUnauthenticated=false", "-o", "Dpkg::Use-Pty=0"]
    result = {"mode": mode, "installed": installed, "architecture": architecture, "source": str(source),
              "keyring": str(key), "key_missing_or_empty": key_needs_repair(key), "profile_code_version": profile_version}
    if mode == "prepare":
        result["key_repaired"] = repair_empty_key(key) if result["key_missing_or_empty"] else False
        result["key_missing_or_empty"] = key_needs_repair(key)
        run(apt + ["-o", "APT::Get::List-Cleanup=false", "-o", "APT::Update::Error-Mode=any", "update"], timeout=110)
    policy = run(["apt-cache", *scope, "-o", "Dir::Cache::pkgcache=", "-o", "Dir::Cache::srcpkgcache=",
                  "policy", "code"]).stdout
    candidate = re.search(r"^\s*Candidate:\s*(\S+)", policy, re.M)
    result["candidate"] = candidate[1] if candidate and PACKAGE_VERSION.fullmatch(candidate[1]) else None
    if mode == "preview":
        return result
    target = requested or result["candidate"]
    if not target:
        raise ValueError("No valid Microsoft Code package version is available")
    if profile_version != "stable" and target != profile_version and not target.startswith(profile_version + "-"):
        raise ValueError(f"The desktop profile pins Code to {profile_version}; choose an approved matching release")
    result["target"] = target
    if target == installed:
        return {**result, "status": "current"}
    if result["key_missing_or_empty"]:
        raise ValueError("The Signed-By keyring is missing or empty; run --prepare first")
    if (REPOSITORY not in policy or
            run(["dpkg", "--compare-versions", installed, "lt", target], check=False).returncode):
        raise ValueError("The target must be a newer Code package from the configured Microsoft source")
    code_names = {"code", f"code:{architecture}"}
    if code_names.intersection(run(["apt-mark", "showhold"]).stdout.splitlines()):
        raise ValueError("Code is on hold; review that Debian setting before updating")
    package = ["--no-install-recommends", "--only-upgrade", "--no-remove", "install", "code=" + target]
    simulation = run(apt + ["-s", *package]).stdout
    changes = re.findall(r"^(Inst|Conf|Remv|Purg) (\S+)", simulation, re.M)
    if (sum(action == "Inst" for action, _ in changes) != 1
            or any(action not in {"Inst", "Conf"} or name not in code_names for action, name in changes)):
        operations = ", ".join(f"{action} {name}" for action, name in changes[:12]) or "no changes"
        raise ValueError(f"The APT simulation must update only Code. Observed {operations}")
    if mode == "prepare":
        run(apt + ["-y", "--download-only", *package], timeout=280)
        return {**result, "status": "prepared"}
    run(apt + ["-y", "--no-download", *package], timeout=None)
    actual, _ = package_status()
    if actual != target:
        raise RuntimeError(f"Code package readback returned {actual}, expected {target}")
    return {**result, "status": "installed", "actual": actual}


if __name__ == "__main__":
    try:
        os.environ.update(LC_ALL="C", DEBIAN_FRONTEND="noninteractive")
        mode, requested, profile_version = sys.argv[1:]
        if mode not in {"preview", "prepare", "apply"} or (mode == "apply" and not requested):
            raise ValueError("Use standalone-code update from native Termux")
        print(json.dumps(update_package(mode, requested, profile_version), ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
