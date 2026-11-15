#!/usr/bin/env python3
"""Install/update Scisaga skills without editing host caches or unknown installs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from skill_repository import (
    DEFAULT_SOURCE,
    DEPENDENCIES,
    LEGACY,
    canonical_skill,
    MARKER,
    MARKETPLACE,
    NAME,
    PLUGIN,
    ROOT,
    SKILLS,
    generated_manifests,
    package,
    read_json,
    render_view,
    repository_digest,
    safe_remove,
    skill_closure,
    skill_files,
    skill_metadata,
    sync_manifests,
    validate_repository,
    view_snapshot,
    write_json,
)


def default_state_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Scisaga/skills"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "scisaga"


class Runner:
    def __init__(self, home: Path | None = None, deadline: float | None = None):
        self.deadline = deadline
        self.env = os.environ.copy()
        if home is not None:
            home = home.resolve()
            (home / ".codex").mkdir(parents=True, exist_ok=True)
            (home / ".claude").mkdir(parents=True, exist_ok=True)
            self.env.update(HOME=str(home), USERPROFILE=str(home),
                            CODEX_HOME=str(home / ".codex"),
                            CLAUDE_CONFIG_DIR=str(home / ".claude"),
                            APPDATA=str(home / "AppData/Roaming"),
                            LOCALAPPDATA=str(home / "AppData/Local"))

    def check_budget(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise RuntimeError("更新超过 60 秒，停止本次更新")

    def run(self, command: list[str], cwd: Path | None = None, timeout: float = 120) -> str:
        self.check_budget()
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
        if timeout <= 0:
            raise RuntimeError("更新超过 60 秒，停止本次更新")
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(command, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RuntimeError(f"命令超时: {command[0]}") from exc
        stdout, stderr = out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
        if process.returncode:
            raise RuntimeError(f"{Path(command[0]).name} 失败 ({process.returncode}): {(stderr or stdout)[-3000:]}")
        return stdout.strip()


def client_command(agent: str) -> list[str]:
    executable = shutil.which("codex" if agent == "codex" else "claude")
    if not executable:
        raise RuntimeError(f"找不到 {agent} 客户端；按 spec/installation-and-updates.md 安装客户端后重试")
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".ps1"}:
        node = shutil.which("node")
        package_name = "@openai/codex" if agent == "codex" else "@anthropic-ai/claude-code"
        for modules in (Path(executable).parent / "node_modules", Path(executable).parent.parent):
            package_root = modules / package_name
            manifest = package_root / "package.json"
            if not manifest.is_file():
                continue
            bins = read_json(manifest).get("bin", {})
            relative = bins if isinstance(bins, str) else bins.get("codex" if agent == "codex" else "claude")
            if not isinstance(relative, str):
                continue
            entry = (package_root / relative).resolve()
            if not entry.is_relative_to(package_root.resolve()) or not entry.is_file():
                continue
            if entry.suffix.lower() == ".exe" and entry.stat().st_size > 1000000:
                return [str(entry)]
            if entry.suffix.lower() in {".js", ".mjs", ".cjs"} and node:
                return [node, str(entry)]
        raise RuntimeError(f"需要原生客户端可执行文件，或可由 Node 直接运行的 CLI: {executable}")
    return [executable]


def git(runner: Runner, root: Path, *args: str) -> str:
    return runner.run(["git", "-C", str(root), *args])


def git_info(runner: Runner, root: Path) -> tuple[str | None, bool]:
    try:
        # An extracted source below another repository is not that parent repository.
        if Path(git(runner, root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
            return None, False
        commit = git(runner, root, "rev-parse", "HEAD")
    except RuntimeError:
        return None, False
    return commit, bool(git(runner, root, "status", "--porcelain"))


def source_identity(root: Path, runner: Runner, fallback: str, is_repository: bool) -> str:
    if not is_repository:
        return fallback
    try:
        return git(runner, root, "remote", "get-url", "origin").removesuffix(".git").lower()
    except RuntimeError:
        return fallback


def load_source(value: str, ref: str, state_dir: Path, runner: Runner, previous: dict | None = None) -> dict:
    path = Path(value).expanduser()
    if path.is_dir():
        root = path.resolve()
        commit, dirty = git_info(runner, root)
        if previous and dirty:
            raise RuntimeError(f"源码有未提交修改，停止更新并保留安装: {root}")
        return {"kind": "local", "path": str(root), "identity": source_identity(root, runner, "local:" + str(root), commit is not None),
                "ref": ref, "commit": commit, "dirty": dirty}
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http", "ssh"} or not parsed.hostname or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("--source 必须为现有目录，或无内嵌凭据的 HTTPS/SSH Git URL")
    if parsed.scheme in {"https", "http"} and parsed.username:
        raise ValueError("Git URL 不得包含凭据")
    if not ref or ref.startswith("-") or re.search(r"[\s\x00-\x1f]", ref):
        raise ValueError("Invalid Git ref")
    identity = value.removesuffix(".git").lower()
    key = hashlib.sha256((identity + "\0" + ref).encode()).hexdigest()[:20]
    cache = state_dir / "sources" / key
    mirror = cache / "mirror.git"
    if previous and previous.get("kind") == "git" and Path(previous["path"]).exists():
        _, dirty = git_info(runner, Path(previous["path"]))
        if dirty:
            raise RuntimeError(f"源码有未提交修改，拒绝覆盖: {previous['path']}")
    cache.mkdir(parents=True, exist_ok=True)
    if not mirror.exists():
        runner.run(["git", "clone", "--mirror", "--", value, str(mirror)])
    runner.run(["git", "--git-dir", str(mirror), "fetch", "origin", ref])
    commit = runner.run(["git", "--git-dir", str(mirror), "rev-parse", "FETCH_HEAD"])
    checkout = cache / "versions" / commit
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        runner.run(["git", "--git-dir", str(mirror), "worktree", "add", "--detach", str(checkout), commit])
    _, dirty = git_info(runner, checkout)
    if dirty:
        raise RuntimeError(f"源码有未提交修改，拒绝覆盖: {checkout}")
    return {"kind": "git", "url": value, "path": str(checkout), "identity": identity,
            "ref": ref, "commit": commit, "dirty": False}


@contextmanager
def state_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manager.lock"
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"另一个管理操作正在运行；若进程已退出，检查并移除锁: {path}") from exc
    try:
        with os.fdopen(handle, "w") as file:
            file.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


class Manager:
    def __init__(self, state_dir: Path, home: Path | None = None, runner: Runner | None = None):
        self.state_dir = state_dir.expanduser().resolve()
        self.home = home.expanduser().resolve() if home else Path.home()
        self.runner = runner or Runner(home)
        self.registry_file = self.state_dir / "installations.json"
        self.registry = read_json(self.registry_file) if self.registry_file.exists() else {"schema": 1, "installations": []}
        if self.registry.get("schema") != 1 or not isinstance(self.registry.get("installations"), list):
            raise ValueError("Unsupported installation registry")

    def save(self):
        write_json(self.registry_file, self.registry)

    def target_dir(self, agent):
        return self.home / (".agents/skills" if agent == "codex" else ".claude/skills")

    def records(self, agent=None, mode=None):
        return [entry for entry in self.registry["installations"]
                if (agent is None or entry["agent"] == agent) and (mode is None or entry["mode"] == mode)]

    def scan_names(self, target: Path, agent="codex"):
        suffixes = (".agents/skills", ".codex/skills") if agent == "codex" else (".claude/skills",)
        roots = {target, *(self.home / suffix for suffix in suffixes)}
        if agent == "codex":
            codex_skills = Path(self.runner.env.get("CODEX_HOME", self.home / ".codex")) / "skills"
            roots.update({codex_skills, codex_skills / ".system", self.home / ".codex/skills/.system"})
        current = Path.cwd().resolve()
        for parent in (current, *current.parents):
            for suffix in suffixes:
                roots.add(parent / suffix)
            if (parent / ".git").exists():
                break
        names: dict[str, list[Path]] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for manifest in root.glob("*/SKILL.md"):
                try:
                    name = skill_metadata(manifest, strict=False)["name"]
                except (ValueError, OSError):
                    # An unreadable/malformed manifest cannot establish a safe free name.
                    name = manifest.parent.name
                names.setdefault(name.casefold(), []).append(manifest.parent.absolute())
        return names

    def owned(self, entry: dict, check_files: bool = True):
        target = Path(entry["target"])
        if not target.is_dir() or not (target / MARKER).is_file():
            raise RuntimeError(f"安装缺失或无归属标记，拒绝覆盖: {target}")
        marker = read_json(target / MARKER)
        if marker.get("owner") != entry["id"]:
            raise RuntimeError(f"安装来源标记不匹配: {target}")
        if check_files:
            current = view_snapshot(target)
            for name, expected in entry["snapshot"].items():
                if current.get(name) != expected:
                    raise RuntimeError(f"安装文件有本地修改，拒绝覆盖: {target / name}")
            extras = set(current) - set(entry["snapshot"])
            # Files outside managed top-level resources are local user data, retained on update.
            managed = {Path(name).parts[0] for name in entry["snapshot"]}
            if any(Path(name).parts[0] in managed and name not in entry.get("local_paths", []) for name in extras):
                raise RuntimeError(f"安装资源中有未登记文件，拒绝覆盖: {target}")
        return target

    def retain_local(self, old: dict, stage: Path):
        """Retain user files at every supported depth without following source links."""
        target = Path(old["target"])
        snapshot = old.get("snapshot", {})
        retained = set()
        for current, directories, files in os.walk(target, followlinks=False):
            self.runner.check_budget()
            here = Path(current)
            for name in list(directories):
                path = here / name
                relative = path.relative_to(target)
                if path.is_symlink():
                    directories.remove(name)
                    if relative.as_posix() in snapshot:
                        continue
                    destination = stage / relative
                    if destination.exists() or destination.is_symlink():
                        raise RuntimeError(f"新版本资源与本地文件冲突，已保留原安装: {path}")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.symlink_to(path.readlink(), target_is_directory=True)
                    retained.add(relative.as_posix())
            for name in files:
                path = here / name
                relative = path.relative_to(target)
                if name == MARKER or relative.as_posix() in snapshot:
                    continue
                destination = stage / relative
                if destination.exists() or destination.is_symlink():
                    raise RuntimeError(f"新版本资源与本地文件冲突，已保留原安装: {path}")
                # A newly linked resource must become a real directory before adding local data.
                for parent in reversed(destination.parents):
                    if parent == stage or not parent.is_relative_to(stage):
                        continue
                    if parent.is_symlink():
                        source = parent.resolve()
                        parent.unlink()
                        shutil.copytree(source, parent)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if path.is_symlink():
                    destination.symlink_to(path.readlink())
                else:
                    shutil.copy2(path, destination)
                retained.add(relative.as_posix())
        return retained

    @staticmethod
    def canonical(entry):
        return canonical_skill(entry["skill"])

    def standalone(self, agent: str, source: dict, selected: list[str] | None,
                   overrides: dict[str, str], copy: bool = False):
        root = Path(source["path"])
        summary = validate_repository(root)
        self.runner.check_budget()
        selected = skill_closure(selected)
        existing = {}
        for entry in self.records(agent, "standalone"):
            if entry["source"]["identity"] != source["identity"]:
                continue
            name = self.canonical(entry)
            if name in existing:
                if name in selected:
                    raise RuntimeError(f"同一技能存在多个已登记版本，保留现状，请先整理: {name}")
                continue
            existing[name] = entry
        aliases = {name: existing[name]["name"] if name in existing else "ss-" + name for name in SKILLS}
        for name, entry in existing.items():
            if entry["skill"] != name and entry["name"] in {entry["skill"], "ss-" + entry["skill"]}:
                aliases[name] = "ss-" + name
        aliases.update(overrides)
        for name, alias in aliases.items():
            if name not in SKILLS or not NAME.fullmatch(alias) or len(alias) > 64:
                raise ValueError(f"Invalid skill/alias: {name}={alias}")
        if len(set(aliases.values())) != len(aliases):
            raise ValueError("安装别名不能重复")
        target_dir = self.target_dir(agent)
        target_dir.mkdir(parents=True, exist_ok=True)
        active_names = self.scan_names(target_dir, agent)
        for name in selected:
            old = existing.get(name)
            if old:
                self.owned(old)
                if old["skill"] == name and old["name"] != aliases[name]:
                    raise ValueError("已安装技能的别名保持不变；如需改名，请先卸载再安装")
            expected = target_dir / aliases[name]
            identity = hashlib.sha256((agent + source["identity"] + "/skills/" + name).encode()).hexdigest()
            if not old and (expected / MARKER).is_file() and not (expected / "SKILL.md").exists():
                retained = read_json(expected / MARKER)
                if retained.get("owner") == identity and retained.get("retained_only"):
                    old = {"id": identity, "target": str(expected), "skill": name,
                           "name": aliases[name], "snapshot": {}}
                    existing[name] = old
            own_paths = {Path(e["target"]).absolute() for e in self.records(mode="standalone")
                         if e["source"]["identity"] == source["identity"] and self.canonical(e) == name}
            conflicts = [p for p in active_names.get(aliases[name].casefold(), []) if p not in own_paths]
            occupied = expected.exists() or expected.is_symlink()
            if conflicts or (occupied and (not old or Path(old["target"]) != expected)):
                raise RuntimeError(f"名称/路径冲突: {aliases[name]}；使用 --alias {name}=另一名称；已有内容未改动")
        for name, old_names in LEGACY.items():
            for legacy_name in (variant for old in old_names for variant in (old, "ss-" + old)):
                legacy_path = target_dir / legacy_name
                if name in selected and legacy_path.exists() and not any(Path(e["target"]) == legacy_path for e in existing.values()):
                    print(f"WARN 旧安装来源未登记，保留原副本: {legacy_path}", file=sys.stderr)
        transaction = Path(tempfile.mkdtemp(prefix=".scisaga-stage-", dir=target_dir))
        replacements, installed = [], []
        try:
            for name in selected:
                target = target_dir / aliases[name]
                identity = hashlib.sha256((agent + source["identity"] + "/skills/" + name).encode()).hexdigest()
                dependencies = {dep: str(target_dir / aliases[dep]) for dep in DEPENDENCIES.get(name, ())}
                stage = transaction / aliases[name]
                marker = render_view(root / "skills" / name, stage, name, aliases, dependencies, identity, copy,
                                     installed_path=target)
                old = existing.get(name)
                local_paths = set()
                if old:
                    local_paths = self.retain_local(old, stage)
                    marker["linked_resources"] = [key for key in marker["linked_resources"] if (stage / key).is_symlink()]
                    write_json(stage / MARKER, marker)
                record = {"id": identity, "agent": agent, "mode": "standalone", "skill": name,
                          "name": aliases[name], "target": str(target), "source": source,
                          "version": summary["version"], "source_sha256": summary["sha256"],
                          "snapshot": {key: value for key, value in view_snapshot(stage).items() if key not in local_paths},
                          "local_paths": sorted(local_paths), "resources": marker["linked_resources"], "copy": copy}
                installed.append(record)
            self.runner.check_budget()
            for record in installed:
                target = Path(record["target"])
                old = existing.get(record["skill"])
                old_target = Path(old["target"]) if old else target
                backup = transaction / (record["name"] + ".previous")
                if old_target.exists():
                    old_target.rename(backup)
                try:
                    (transaction / record["name"]).rename(target)
                except BaseException:
                    if backup.exists():
                        backup.rename(old_target)
                    raise
                replacements.append((target, backup, old_target))
            previous = list(self.registry["installations"])
            self.runner.check_budget()
            ids = {record["id"] for record in installed} | {existing[name]["id"] for name in selected if name in existing}
            self.registry["installations"] = [entry for entry in previous if entry["id"] not in ids] + installed
            try:
                self.save()
            except BaseException:
                self.registry["installations"] = previous
                raise
        except BaseException:
            for target, backup, old_target in reversed(replacements):
                if target.exists():
                    safe_remove(target, target_dir)
                if backup.exists():
                    backup.rename(old_target)
            raise
        finally:
            safe_remove(transaction, target_dir)
        return {"installed": [{key: r[key] for key in ("skill", "name", "target", "version", "resources")}
                              for r in installed], "sha256": summary["sha256"]}

    def local_marketplace(self, source: dict, summary: dict, agent: str) -> Path:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        catalog = self.state_dir / "marketplaces" / agent
        package_root = catalog / "packages" / summary["sha256"]
        if not package_root.exists():
            stage = Path(tempfile.mkdtemp(prefix=".package-", dir=self.state_dir))
            try:
                root = Path(source["path"])
                for rel in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
                    destination = stage / rel
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / rel, destination)
                for name in SKILLS:
                    for rel, path in skill_files(root / "skills" / name):
                        self.runner.check_budget()
                        destination = stage / "skills" / name / rel
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, destination)
                package_root.parent.mkdir(parents=True, exist_ok=True)
                stage.rename(package_root)
            finally:
                if stage.exists():
                    safe_remove(stage, self.state_dir)
        manifests = generated_manifests(Path(source["path"]))
        codex = manifests[".agents/plugins/marketplace.json"]
        codex["plugins"][0]["source"]["path"] = "./packages/" + summary["sha256"]
        claude = manifests[".claude-plugin/marketplace.json"]
        claude["plugins"][0]["source"] = "./packages/" + summary["sha256"]
        write_json(catalog / ".agents/plugins/marketplace.json", codex)
        write_json(catalog / ".claude-plugin/marketplace.json", claude)
        return catalog

    def native(self, agent: str, *args: str):
        return self.runner.run(client_command(agent) + list(args))

    def native_inventory(self, agent: str, independent: bool = False):
        runner = self.runner
        if independent:
            runner = Runner(deadline=time.monotonic() + 5)
            runner.env = self.runner.env.copy()
        plugins = json.loads(runner.run(client_command(agent) + ["plugin", "list", "--json"]))
        marketplaces = json.loads(runner.run(client_command(agent) + ["plugin", "marketplace", "list", "--json"]))
        if isinstance(plugins, dict):
            plugins = plugins.get("installed", [])
        if isinstance(marketplaces, dict):
            marketplaces = marketplaces.get("marketplaces", [])
        if not isinstance(plugins, list) or not isinstance(marketplaces, list):
            raise RuntimeError("客户端插件清单格式无法识别，停止修改")  # noqa: TRY004 -- invalid external JSON
        return plugins, marketplaces

    @staticmethod
    def plugin_id(row):
        return row.get("pluginId", row.get("id", row.get("name", "")))

    @staticmethod
    def marketplace_identity(row):
        return {key: row[key] for key in ("name", "root", "source", "url", "repo", "path", "ref", "installLocation") if key in row}

    def plugin_preflight(self, agent, previous, source_identity=None):
        plugins, marketplaces = self.native_inventory(agent)
        matching = [row for row in plugins if self.plugin_id(row).split("@", 1)[0] == PLUGIN]
        markets = [row for row in marketplaces if row.get("name") == MARKETPLACE]
        if not previous:
            known = self.registry.get("marketplaces", {}).get(agent, {})
            own_market = (known.get("source_identity") == source_identity and len(markets) == 1 and
                          self.marketplace_identity(markets[0]) == known.get("native_marketplace"))
            if matching or (markets and not own_market):
                raise RuntimeError("原生客户端已有未登记的 scisaga 插件或 scisaga-skills marketplace；保留原配置，可使用独立技能别名安装")
        if previous:
            if any(self.plugin_id(row) != f"{PLUGIN}@{MARKETPLACE}" for row in matching):
                raise RuntimeError("其他 marketplace 中有同名 scisaga 插件，停止覆盖")
            expected = previous[0].get("native_marketplace")
            if expected and (len(markets) != 1 or self.marketplace_identity(markets[0]) != expected):
                raise RuntimeError("marketplace 来源已在客户端中改变，保留现有配置")

    def plugin_install(self, agent: str, source: dict, update: bool = False):
        summary = validate_repository(Path(source["path"]))
        self.runner.check_budget()
        previous = self.records(agent, "plugin")
        if previous and previous[0]["source"]["identity"] != source["identity"]:
            raise RuntimeError("scisaga 插件已由另一来源管理，拒绝覆盖；可改用独立技能别名安装")
        if previous and previous[0]["version"] == summary["version"] and previous[0]["source_sha256"] != summary["sha256"]:
            raise RuntimeError("插件内容已更改但版本未递增；先运行 package --bump patch，再更新")
        self.plugin_preflight(agent, previous, source["identity"])
        # Claude's #ref clone accepts branches/tags but rejects raw commit IDs.
        # Register an immutable, sanitized local catalog for a pinned commit instead.
        local_catalog = source["kind"] == "local" or (
            agent == "claude-code" and re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", source["ref"]))
        if local_catalog:
            location = str(self.local_marketplace(source, summary, agent))
        else:
            location = source["url"]
        if agent == "codex":
            args = ["plugin", "marketplace", "add", location, "--json"]
            if source["kind"] == "git":
                args += ["--ref", source["ref"]]
            self.native(agent, *args)
            if update and source["kind"] == "git":
                self.native(agent, "plugin", "marketplace", "upgrade", MARKETPLACE, "--json")
            result = self.native(agent, "plugin", "add", f"{PLUGIN}@{MARKETPLACE}", "--json")
        else:
            if source["kind"] == "git" and not local_catalog:
                location += "#" + source["ref"]
            self.native(agent, "plugin", "marketplace", "add", location)
            if update:
                self.native(agent, "plugin", "marketplace", "update", MARKETPLACE)
                result = self.native(agent, "plugin", "update", f"{PLUGIN}@{MARKETPLACE}")
            else:
                result = self.native(agent, "plugin", "install", f"{PLUGIN}@{MARKETPLACE}", "--scope", "user")
        plugins, marketplaces = self.native_inventory(agent)
        active = [row for row in plugins if self.plugin_id(row) == f"{PLUGIN}@{MARKETPLACE}"]
        if len(active) != 1 or active[0].get("enabled") is False or active[0].get("version") != summary["version"]:
            raise RuntimeError("客户端未启用预期插件版本，安装记录未更新")
        cache = self.find_plugin_cache(agent, summary["version"], active[0].get("installPath"))
        if repository_digest(cache) != summary["sha256"]:
            raise RuntimeError("客户端插件文件与已验证源码摘要不一致，安装记录未更新")
        market = next((row for row in marketplaces if row.get("name") == MARKETPLACE), None)
        if market is None:
            raise RuntimeError("客户端缺少预期 marketplace，安装记录未更新")
        record = {"id": agent + ":plugin:" + PLUGIN, "agent": agent, "mode": "plugin",
                  "name": PLUGIN, "source": source, "version": summary["version"],
                  "source_sha256": summary["sha256"], "target": str(cache),
                  "marketplace": MARKETPLACE, "native_marketplace": self.marketplace_identity(market)}
        self.registry["installations"] = [e for e in self.registry["installations"] if e["id"] != record["id"]] + [record]
        self.registry.setdefault("marketplaces", {})[agent] = {
            "source_identity": source["identity"], "native_marketplace": record["native_marketplace"]}
        self.save()
        return {"installed": record["name"], "agent": agent, "version": summary["version"],
                "target": str(cache), "sha256": summary["sha256"], "client": result}

    def find_plugin_cache(self, agent: str, version: str | None = None, native_path: str | None = None) -> Path:
        if agent == "codex":
            base = Path(self.runner.env.get("CODEX_HOME", self.home / ".codex")) / "plugins/cache" / MARKETPLACE / PLUGIN
        else:
            base = Path(self.runner.env.get("CLAUDE_CONFIG_DIR", self.home / ".claude")) / "plugins/cache" / MARKETPLACE / PLUGIN
        candidates = ([Path(native_path)] if native_path else []) + [base] + (sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if base.is_dir() else [])
        for candidate in candidates:
            manifest = candidate / "plugin.json"
            if manifest.is_file():
                info = read_json(manifest)
                if info.get("name") == PLUGIN and (version is None or info.get("version") == version):
                    if {p.parent.name for p in (candidate / "skills").glob("*/SKILL.md")} != set(SKILLS):
                        continue
                    return candidate
        raise RuntimeError(f"客户端未提供预期插件版本 {version or ''}，安装记录未更新；请检查客户端插件状态")

    def usable(self, entry: dict) -> bool:
        try:
            if entry["mode"] == "standalone":
                self.owned(entry)
                for dep in DEPENDENCIES.get(self.canonical(entry), ()):
                    dependency = next((candidate for candidate in self.records(entry["agent"], "standalone")
                                       if self.canonical(candidate) == dep
                                       and candidate["source"]["identity"] == entry["source"]["identity"]), None)
                    if dependency is None:
                        return False
                    self.owned(dependency)
                    marker = read_json(Path(entry["target"]) / MARKER)
                    if marker.get("dependencies", {}).get(dep) != dependency["target"]:
                        return False
                return True
            plugins, _ = self.native_inventory(entry["agent"], independent=True)
            active = next((row for row in plugins if self.plugin_id(row) == f"{PLUGIN}@{MARKETPLACE}"), None)
            if not active or active.get("enabled") is False or active.get("installed") is False:
                return False
            cache = self.find_plugin_cache(entry["agent"], active.get("version"), active.get("installPath"))
            return active.get("version") != entry["version"] or repository_digest(cache) == entry["source_sha256"]
        except (RuntimeError, OSError, ValueError):
            return False

    def update(self, agent=None, mode=None, selected=None, names=None):
        records = self.records(agent, mode)
        if names:
            records = [entry for entry in records if entry["name"] in names]
            missing = set(names) - {entry["name"] for entry in records}
            if missing:
                raise RuntimeError(f"没有匹配的已登记安装名称: {sorted(missing)}")
            dependencies = []
            for entry in records:
                if entry["mode"] != "standalone":
                    continue
                for dep in skill_closure([self.canonical(entry)]):
                    dependencies += [candidate for candidate in self.records(agent, "standalone")
                                     if candidate["source"]["identity"] == entry["source"]["identity"]
                                     and self.canonical(candidate) == dep and candidate not in records]
            for entry in dependencies:
                if entry not in records:
                    records.append(entry)
        if selected:
            if mode == "plugin":
                raise ValueError("插件整体更新，不支持 --skill")
            wanted = skill_closure(selected)
            records = [entry for entry in records if self.canonical(entry) in wanted]
        if not records:
            raise RuntimeError("没有已登记安装；请先 install")
        results = []
        groups = {}
        for entry in records:
            key = (entry["agent"], entry["mode"], entry["source"]["identity"], entry["source"]["ref"])
            groups.setdefault(key, []).append(entry)
        for (client, kind, _, ref), entries in groups.items():
            old = entries[0]["source"]
            source = load_source(old.get("url", old["path"]), ref, self.state_dir, self.runner, old)
            if kind == "plugin":
                results.append(self.plugin_install(client, source, update=True))
            else:
                results.append(self.standalone(client, source, [self.canonical(e) for e in entries],
                                               {self.canonical(e): e["name"] for e in entries if self.canonical(e) == e["skill"]
                                                or e["name"] not in {e["skill"], "ss-" + e["skill"]}},
                                               copy=any(e.get("copy") for e in entries)))
        return {"updated": results}

    def uninstall(self, agent, mode, selected, names=None):
        selected = [canonical_skill(name) for name in selected] if selected else selected
        entries = [e for e in self.records(agent, mode) if (not names or e["name"] in names)
                   and (mode == "plugin" or not selected or self.canonical(e) in selected)]
        if names and set(names) - {entry["name"] for entry in entries}:
            raise RuntimeError("没有匹配的已登记安装名称，未执行卸载")
        if not entries:
            raise RuntimeError("没有匹配的已登记安装")
        for entry in entries:
            if entry["mode"] == "standalone":
                self.owned(entry)
                for dependent in self.records(agent, mode):
                    if (dependent not in entries and self.canonical(entry) in DEPENDENCIES.get(self.canonical(dependent), ())
                            and dependent["source"]["identity"] == entry["source"]["identity"]):
                        raise RuntimeError(f"{dependent['name']} 仍依赖 {entry['name']}，请一并卸载")
            else:
                self.plugin_preflight(agent, [entry])
        removed = []
        for entry in entries:
            if mode == "plugin":
                command = "remove" if agent == "codex" else "uninstall"
                self.native(agent, "plugin", command, f"{PLUGIN}@{MARKETPLACE}")
                if entry.get("native_marketplace"):
                    self.registry.setdefault("marketplaces", {})[agent] = {
                        "source_identity": entry["source"]["identity"], "native_marketplace": entry["native_marketplace"]}
            else:
                target = Path(entry["target"])
                for name in sorted(entry["snapshot"], key=lambda value: -len(Path(value).parts)):
                    safe_remove(target / name, target)
                (target / MARKER).unlink()
                for current, _, _ in os.walk(target, topdown=False, followlinks=False):
                    path = Path(current)
                    if path != target and not any(path.iterdir()):
                        path.rmdir()
                if not any(target.iterdir()):
                    target.rmdir()
                else:
                    write_json(target / MARKER, {"schema": 1, "owner": entry["id"], "retained_only": True,
                                                "source_identity": entry["source"]["identity"], "name": entry["name"]})
                    print(f"INFO 保留本地配置/运行文件: {target}", file=sys.stderr)
            self.registry["installations"].remove(entry)
            removed.append(entry["name"])
        self.save()
        return {"uninstalled": removed}


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--home-dir", type=Path, default=argparse.SUPPRESS, help="隔离安装目标及原生客户端配置目录")
    result = argparse.ArgumentParser(description=__doc__, parents=[common])
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("install", "update", "check", "doctor", "uninstall"):
        command = commands.add_parser(name, parents=[common])
        command.add_argument("--agent", choices=("codex", "claude-code"), default="codex")
        command.add_argument("--mode", choices=("plugin", "standalone"), default="plugin")
        command.add_argument("--skill", type=canonical_skill, choices=SKILLS, action="append")
        if name != "install":
            command.add_argument("--name", action="append", help="只处理指定安装名称/别名，可重复")
        if name == "install":
            command.add_argument("--source", default=DEFAULT_SOURCE)
            command.add_argument("--ref", default="main")
            command.add_argument("--alias", action="append", default=[], metavar="SKILL=NAME")
            command.add_argument("--copy", action="store_true")
        if name in {"check", "doctor"}:
            command.add_argument("--repository", type=Path, default=ROOT)
            command.add_argument("--remote", action="store_true", help="额外检查已登记 Git 来源的远端提交")
    build = commands.add_parser("package", parents=[common])
    build.add_argument("--repository", type=Path, default=ROOT)
    build.add_argument("--output", type=Path, default=ROOT / "dist/scisaga.zip")
    build.add_argument("--sync-manifests", action="store_true")
    build.add_argument("--bump", choices=("patch", "minor", "major"))
    launch = commands.add_parser("launch", parents=[common])
    launch.add_argument("client", choices=("codex",))
    launch.add_argument("args", nargs=argparse.REMAINDER)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if getattr(args, "mode", None) == "plugin" and getattr(args, "skill", None):
        raise ValueError("插件以整体管理，--skill 仅用于独立技能模式")
    manager = Manager(getattr(args, "state_dir", default_state_dir()), getattr(args, "home_dir", None))
    if args.command == "package":
        if args.bump:
            manifest = read_json(args.repository / "plugin.json")
            major, minor, patch = map(int, manifest["version"].split("."))
            manifest["version"] = {"patch": f"{major}.{minor}.{patch + 1}",
                                   "minor": f"{major}.{minor + 1}.0", "major": f"{major + 1}.0.0"}[args.bump]
            write_json(args.repository / "plugin.json", manifest)
        if args.sync_manifests or args.bump:
            sync_manifests(args.repository)
        output = package(args.repository.resolve(), args.output)
    elif args.command in {"check", "doctor"}:
        output = validate_repository(args.repository.resolve())
        installed = manager.records(args.agent, args.mode)
        if args.skill:
            selected = skill_closure(args.skill)
            installed = [entry for entry in installed if manager.canonical(entry) in selected]
        if args.name:
            installed = [entry for entry in installed if entry["name"] in args.name]
            if not installed:
                raise RuntimeError("没有匹配的已登记安装名称")
        output["installations"] = [{"name": e["name"], "version": e["version"], "usable": manager.usable(e)} for e in installed]
        names = manager.scan_names(manager.target_dir(args.agent), args.agent)
        output["conflicts"] = {name: [str(path) for path in paths] for name, paths in names.items() if len(set(paths)) > 1}
        output["updates"] = []
        for entry in installed:
            source = entry["source"]
            if source["kind"] == "local" and (Path(source["path"]) / "plugin.json").is_file():
                current = repository_digest(Path(source["path"]))
                output["updates"].append({"name": entry["name"], "available": current != entry["source_sha256"]})
        if any(not row["usable"] for row in output["installations"]):
            raise RuntimeError("安装检查失败: " + json.dumps(output, ensure_ascii=False))
        if output["conflicts"]:
            raise RuntimeError("注册名称冲突: " + json.dumps(output, ensure_ascii=False))
        if args.command == "doctor":
            output["python"] = sys.version.split()[0]
            output["git"] = manager.runner.run(["git", "--version"])
            if args.mode == "plugin":
                output["client"] = manager.runner.run(client_command(args.agent) + ["--version"])
                plugins, marketplaces = manager.native_inventory(args.agent)
                output["native_plugin_commands"] = {"installed": len(plugins), "marketplaces": len(marketplaces)}
            output["paths"] = {"state": str(manager.state_dir), "skills": str(manager.target_dir(args.agent))}
        if args.remote:
            updates = []
            for entry in installed:
                source = entry["source"]
                if source["kind"] != "git":
                    continue
                remote = manager.runner.run(["git", "ls-remote", source["url"], source["ref"]])
                updates.append({"name": entry["name"], "available": bool(remote and remote.split()[0] != source["commit"])})
            output["updates"].extend(updates)
    elif args.command == "launch":
        manager.runner.deadline = time.monotonic() + 60
        existing = manager.records("codex")
        try:
            with state_lock(manager.state_dir):
                manager.update("codex")
        except (RuntimeError, OSError, ValueError) as exc:
            print(f"WARN 启动前更新失败: {exc}", file=sys.stderr)
            if not existing or not all(manager.usable(entry) for entry in existing):
                raise RuntimeError("没有可用的已登记 Codex 安装，停止启动") from exc
            print("INFO 使用上一个可用版本启动", file=sys.stderr)
        forwarded = args.args[1:] if args.args[:1] == ["--"] else args.args
        return subprocess.call(client_command("codex") + forwarded, env=manager.runner.env)
    else:
        with state_lock(manager.state_dir):
            if args.command == "install":
                source = load_source(args.source, args.ref, manager.state_dir, manager.runner)
                overrides = {}
                for value in args.alias:
                    if "=" not in value:
                        raise ValueError("--alias 格式为 SKILL=NAME")
                    name, alias = value.split("=", 1)
                    name = canonical_skill(name)
                    if name in overrides:
                        raise ValueError("重复的 --alias")
                    overrides[name] = alias
                if args.mode == "plugin":
                    if args.alias or args.skill or args.copy:
                        raise ValueError("插件安装包含全部技能；--skill/--alias/--copy 仅用于独立安装")
                    output = manager.plugin_install(args.agent, source)
                else:
                    output = manager.standalone(args.agent, source, args.skill, overrides, args.copy)
            elif args.command == "update":
                output = manager.update(args.agent, args.mode, args.skill, args.name)
            else:
                output = manager.uninstall(args.agent, args.mode, args.skill, args.name)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
