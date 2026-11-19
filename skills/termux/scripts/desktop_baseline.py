#!/usr/bin/env python3
"""Compare saved desktop readbacks and verify the files in a recovery bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from desktop_profile import profile_digest, validate_profile


SECTIONS = ("native_profile", "packages", "xfce", "code", "mime", "files")
PROFILE_PROPERTIES = (
    ("xfwm4", "/general/use_compositing", "window_compositing"),
    ("xfwm4", "/general/vblank_mode", "window_vblank_mode"),
    ("xfwm4", "/general/theme", "titlebar_theme"),
    ("xsettings", "/Net/ThemeName", "theme"),
)


def unique_object(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError(f"Duplicate JSON key: {key}")
        values[key] = value
    return values


def read_json(path):
    data = path.read_bytes()
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value, hashlib.sha256(data).hexdigest()


def asset_path(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name
            or any(part in (".", "..") or not re.fullmatch(r"[\w.@ -]+", part) for part in path.parts)):
        raise ValueError(f"Invalid relative asset path: {name!r}")
    if not path.parts:
        raise ValueError("Empty asset path")
    return path


def read_manifest(path):
    value, digest = read_json(path)
    if type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("Expected desktop baseline schema 1")
    if not isinstance(value.get("architecture"), str) or not value["architecture"]:
        raise ValueError("Manifest must record its architecture")
    for section in SECTIONS:
        if not isinstance(value.get(section), dict):
            raise ValueError(f"Manifest must record a {section} object")
    if any(not isinstance(settings, dict) for settings in value["xfce"].values()):
        raise ValueError("Xfce channels must contain settings objects")
    for name, info in value["files"].items():
        asset_path(name)
        if (not isinstance(info, dict) or type(info.get("size")) is not int or info["size"] < 0
                or not isinstance(info.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", info["sha256"])
                or type(info.get("mode")) is not int or not 0 <= info["mode"] <= 0o777):
            raise ValueError(f"Invalid asset metadata: {name}")
    return value, digest


def changed_paths(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            item = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key in before and key in after:
                yield from changed_paths(before[key], after[key], item)
            else:
                yield item
    elif json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True):
        yield path


def compare(baseline, current, allow_change):
    before, before_digest = read_manifest(baseline)
    after, after_digest = read_manifest(current)
    changes = sorted(changed_paths(before, after))
    unexpected = sorted(set(changes) - set(allow_change))
    return {
        "status": "drift" if unexpected else "passed",
        "baseline_sha256": before_digest,
        "current_sha256": after_digest,
        "allowed_changes": sorted(set(allow_change)),
        "changed": changes,
        "unexpected": unexpected,
    }


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(bundle):
    manifest, manifest_digest = read_manifest(bundle / "manifest.json")
    requested, requested_digest = read_json(bundle / "profile.json")
    plan = validate_profile(requested)
    root = bundle.resolve() / "files"
    mismatched_files = []
    for name, info in sorted(manifest["files"].items()):
        path = root.joinpath(*asset_path(name).parts)
        if (path.resolve() != path or not path.is_file() or path.stat().st_size != info["size"]
                or file_sha256(path) != info["sha256"]):
            mismatched_files.append(name)
    mismatched_profile = []
    for channel, prop, key in PROFILE_PROPERTIES:
        observed = manifest["xfce"].get(channel, {}).get(prop)
        if observed is None:
            continue
        planned = str(plan[key]).lower() if isinstance(plan[key], bool) else plan[key]
        if isinstance(observed, bool):
            observed = str(observed).lower()
        if observed != planned:
            mismatched_profile.append(key)
    return {
        "status": "drift" if mismatched_files or mismatched_profile else "passed",
        "manifest_sha256": manifest_digest,
        "profile_input_sha256": requested_digest,
        "profile_sha256": profile_digest(plan),
        "asset_count": len(manifest["files"]),
        "mismatched_files": mismatched_files,
        "mismatched_profile": mismatched_profile,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    diff = commands.add_parser("compare", help="Compare two saved readbacks")
    diff.add_argument("--baseline", type=Path, required=True)
    diff.add_argument("--current", type=Path, required=True)
    diff.add_argument("--allow-change", action="append", default=[], metavar="JSON_POINTER")
    verify = commands.add_parser("verify", help="Verify an unpacked recovery bundle")
    verify.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (compare(args.baseline, args.current, args.allow_change) if args.command == "compare"
                  else verify_bundle(args.bundle))
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
