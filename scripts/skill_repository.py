"""Repository manifests, validated file selection and standalone skill views."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = "scisaga"
MARKETPLACE = "scisaga-skills"
DEFAULT_SOURCE = "https://github.com/Scisaga/skills.git"
SKILLS = ("termux", "slides", "dev-ops", "domain-manager", "gitlab-issue",
          "pdf", "speech", "subtitle-matcher", "video")
DEPENDENCIES = {"video": ("speech",)}
LEGACY = {"slides": ("build-narrated-presentation",),
          "termux": ("termux-ssh", "android-termux-ssh")}
MARKER = ".scisaga-install.json"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
DENIED = {".git", ".venv", ".venv-win", "venv", "env", "__pycache__",
          ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".build",
          "node_modules", "out", "output", "outputs", "tmp", "temp"}
RESOURCE_DIRS = {"scripts", "references", "assets", "agents", "tests"}
ROOT_FILES = {"SKILL.md", "requirements.txt", "requirements-azure.txt"}


def yaml_module():
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少 PyYAML；安装：python -m pip install -r requirements-tools.txt") from exc
    return yaml


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")  # noqa: TRY004 -- invalid file contents
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".scisaga-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def skill_metadata(path: Path, strict: bool = True) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError(f"Missing skill frontmatter: {path}")
    value = yaml_module().safe_load(match.group(1))
    if not isinstance(value, dict) or (strict and set(value) != {"name", "description"}):
        raise ValueError(f"Skill frontmatter must contain only name and description: {path}")
    if not isinstance(value.get("name"), str) or not NAME.fullmatch(value["name"]) or len(value["name"]) > 64:
        raise ValueError(f"Invalid skill name: {path}")
    if strict and (not isinstance(value.get("description"), str) or not value["description"].strip()):
        raise ValueError(f"Missing skill description: {path}")
    return value


def allowed(relative: Path) -> bool:
    return not any(part in DENIED or (part.startswith(".env") and part != ".env.example")
                   or part.endswith((".pyc", ".log", ".tmp")) for part in relative.parts)


def skill_files(skill: Path):
    """Allowlisted roots; never traverse source links or include runtime state."""
    for current, directories, files in os.walk(skill, followlinks=False):
        current_path = Path(current)
        rel = current_path.relative_to(skill)
        directories[:] = sorted(d for d in directories if allowed(rel / d)
                                and (rel.parts or d in RESOURCE_DIRS))
        for directory in directories:
            if (current_path / directory).is_symlink():
                raise ValueError(f"Source symlink is not publishable: {current_path / directory}")
        for name in sorted(files):
            relative = rel / name
            if not allowed(relative) or (not rel.parts and name not in ROOT_FILES):
                continue
            source = current_path / name
            if source.is_symlink():
                raise ValueError(f"Source symlink is not publishable: {source}")
            yield relative, source


def digest_files(files) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(files, key=lambda item: str(item[0])):
        digest.update(str(name).replace("\\", "/").encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def repository_digest(root: Path) -> str:
    files = [(Path("plugin.json"), root / "plugin.json")]
    files += [(Path(name), root / name) for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")]
    for name in SKILLS:
        files.extend((Path("skills") / name / rel, source)
                     for rel, source in skill_files(root / "skills" / name))
    return digest_files(files)


def generated_manifests(root: Path) -> dict[str, dict]:
    manifest = read_json(root / "plugin.json")
    common = {key: manifest[key] for key in ("name", "version", "description", "author")}
    codex = dict(common, skills="./skills/",
                 interface=manifest.get("extensions", {}).get("com.openai", {}).get("interface", {}))
    return {
        ".codex-plugin/plugin.json": codex,
        ".claude-plugin/plugin.json": dict(common, displayName=codex["interface"].get("displayName", PLUGIN)),
        ".agents/plugins/marketplace.json": {
            "name": MARKETPLACE, "interface": {"displayName": "Scisaga Skills"},
            "plugins": [{"name": PLUGIN, "source": {"source": "local", "path": "./"},
                         "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                         "category": "Productivity"}]},
        ".claude-plugin/marketplace.json": {
            "name": MARKETPLACE, "owner": manifest["author"], "description": manifest["description"],
            "plugins": [{"name": PLUGIN, "source": "./", "version": manifest["version"],
                         "description": manifest["description"]}]},
    }


def sync_manifests(root: Path) -> None:
    for name, content in generated_manifests(root).items():
        write_json(root / name, content)


def _validate_repository(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "plugin.json")
    if manifest.get("name") != PLUGIN or manifest.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        raise ValueError("Invalid portable plugin identity/schema")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", manifest.get("version", "")):
        raise ValueError("Plugin version must be SemVer")
    actual = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}
    if actual != set(SKILLS):
        raise ValueError(f"Skill inventory mismatch: {sorted(actual)}")
    for name, expected in generated_manifests(root).items():
        if read_json(root / name) != expected:
            raise ValueError(f"Generated manifest out of date: {name}; run package --sync-manifests")
    for name in SKILLS:
        skill = root / "skills" / name
        metadata = skill_metadata(skill / "SKILL.md")
        if metadata["name"] != name:
            raise ValueError(f"Skill name/directory mismatch: {name}")
        agent = yaml_module().safe_load((skill / "agents/openai.yaml").read_text(encoding="utf-8-sig"))
        ui = agent.get("interface", {}) if isinstance(agent, dict) else {}
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", ui.get("brand_color", "")):
            raise ValueError(f"Invalid brand color: {name}")
        for key in ("icon_small", "icon_large"):
            target = (skill / ui.get(key, "")).resolve()
            if not target.is_relative_to(skill.resolve()) or not target.is_file():
                raise ValueError(f"Missing/escaping icon: {name}/{key}")
        if not (skill / "assets/logo.svg").is_file():
            raise ValueError(f"Missing skill logo: {name}")
        if ElementTree.parse(skill / "assets/logo.svg").getroot().tag.rsplit("}", 1)[-1] != "svg":
            raise ValueError(f"Invalid SVG logo: {name}")
        list(skill_files(skill))
        for document in (skill / "SKILL.md", *skill.glob("references/*.md")):
            text = document.read_text(encoding="utf-8-sig")
            for link in re.findall(r"\]\(<?([^\s)]+)>?\)", text):
                link = link.rstrip(">")
                if "://" in link or link.startswith(("#", "mailto:")) or "$" in link:
                    continue
                target = document.parent / link.split("#", 1)[0]
                if not target.exists():
                    raise ValueError(f"Broken Markdown link: {document.relative_to(root)} -> {link}")
    return {"plugin": PLUGIN, "version": manifest["version"], "skills": list(SKILLS),
            "sha256": repository_digest(root)}


def validate_repository(root: Path) -> dict[str, Any]:
    try:
        return _validate_repository(root)
    except (OSError, ValueError, RuntimeError, ElementTree.ParseError) as exc:
        # The blocking gate always identifies the input, even for a malformed manifest.
        inputs = []
        for path in (root / "plugin.json", *(root / "skills").glob("*/SKILL.md"),
                     *(root / "skills").glob("*/agents/openai.yaml")):
            if path.is_file() and not path.is_symlink():
                inputs.append((path.relative_to(root), path))
        try:
            digest = repository_digest(root)
        except (OSError, ValueError):
            digest = digest_files(inputs)
        raise ValueError(f"{exc}; input_repository={root}; input_sha256={digest}") from exc


def canonical_skill(name: str) -> str:
    return next((new for new, old_names in LEGACY.items() if name in old_names), name)


def skill_closure(selected: list[str] | None) -> list[str]:
    result = []
    def visit(name):
        name = canonical_skill(name)
        if name not in SKILLS:
            raise ValueError(f"Unknown skill: {name}")
        for dependency in DEPENDENCIES.get(name, ()):
            visit(dependency)
        if name not in result:
            result.append(name)
    for name in selected or SKILLS:
        visit(name)
    return result


def replace_mentions(text: str, names: dict[str, str]) -> str:
    for name, alias in sorted(names.items(), key=lambda row: -len(row[0])):
        text = re.sub(r"\$(?:scisaga:)?" + re.escape(name) + r"(?![a-z0-9-])",
                      lambda _, alias=alias: "$" + alias, text)
    return text


def render_view(source: Path, destination: Path, name: str, aliases: dict[str, str],
                dependency_paths: dict[str, str], owner: str, copy: bool = False,
                installed_path: Path | None = None) -> dict:
    destination.mkdir(parents=True)
    used = []
    skill_metadata(source / "SKILL.md")
    install_root = (installed_path or destination).absolute()

    def installed_text(text):
        text = replace_mentions(text, aliases)
        names = "|".join(re.escape(key) for key in aliases)
        for original in aliases:
            text = text.replace("/absolute/path/to/" + original + "/", "skills/" + original + "/")
        text = re.sub(r"(?:\.\\)?skills\\(?P<skill>" + names + r")\\(?P<tail>[^\s`\"'<>;|]+)",
                      lambda match: "skills/" + match.group("skill") + "/" + match.group("tail").replace("\\", "/"), text)

        def command(match):
            prefix = match.group("prefix")
            path = (install_root.parent / aliases[match.group("skill")]).as_posix() + "/" + match.group("tail")
            quoted = "'" + path.replace("'", "''") + "'" if prefix.strip() in {"&", "-File"} else shlex.quote(path)
            return prefix + quoted

        text = re.sub(r"(?P<prefix>(?:\bbash|\bsh|\bpython(?:3)?|\bpwsh|&|-File)\s+)"
                      r"skills/(?P<skill>" + names + r")/(?P<tail>[^\s`\"'<>;|]+)", command, text)
        text = re.sub(r"(?m)^(?P<indent>\s*)(?P<prefix>)skills/(?P<skill>" + names +
                      r")/(?P<tail>[^\s`\"'<>;|]+\.sh)(?=\s|$)",
                      lambda match: match.group("indent") + "bash " + command(match), text)
        for original, alias in sorted(aliases.items(), key=lambda row: -len(row[0])):
            # Commands become independent of the caller's working directory.
            text = text.replace("skills/" + original + "/", (install_root.parent / alias).as_posix() + "/")
            text = text.replace("../" + original + "/", "../" + alias + "/")
        return text

    text = (source / "SKILL.md").read_text(encoding="utf-8-sig")
    text = re.sub(r"(?m)^name:.*$", "name: " + aliases[name], text, count=1)
    text = installed_text(text)
    (destination / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")
    # Validate the entire selected resource tree before linking any directory.
    list(skill_files(source))
    for item in source.iterdir():
        if item.name not in (RESOURCE_DIRS | ROOT_FILES) or item.name == "SKILL.md":
            continue
        target = destination / item.name
        if item.name == "agents":
            target.mkdir()
            for rel, path in ((p.relative_to(item), p) for p in item.rglob("*") if p.is_file()):
                if not allowed(rel):
                    continue
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                content = installed_text(path.read_text(encoding="utf-8-sig"))
                if rel.as_posix() == "openai.yaml":
                    metadata = yaml_module().safe_load(content)
                    metadata.setdefault("interface", {})["display_name"] = aliases[name]
                    content = yaml_module().safe_dump(metadata, allow_unicode=True, sort_keys=False)
                out.write_text(content, encoding="utf-8")
        elif item.is_file():
            shutil.copy2(item, target)
        else:
            # A dirty resource directory may contain local .env/cache files: only copy its allowlist.
            safe_paths = {str(rel) for rel, _ in skill_files(source) if rel.parts[0] == item.name}
            actual_paths = {str(p.relative_to(source)) for p in item.rglob("*") if p.is_file()}
            linked = False
            changed_docs = item.name == "references" and any(
                path.suffix == ".md" and installed_text(path.read_text(encoding="utf-8-sig")) != path.read_text(encoding="utf-8-sig")
                for _, path in skill_files(source) if path.parent.is_relative_to(item))
            if not copy and actual_paths == safe_paths and not changed_docs:
                try:
                    target.symlink_to(item.resolve(), target_is_directory=True)
                    linked = True
                except OSError:
                    pass
            if linked:
                used.append(item.name)
            else:
                for rel, path in skill_files(source):
                    if rel.parts[0] == item.name:
                        out = destination / rel
                        out.parent.mkdir(parents=True, exist_ok=True)
                        if item.name == "references" and path.suffix == ".md":
                            out.write_text(installed_text(path.read_text(encoding="utf-8-sig")), encoding="utf-8")
                        else:
                            shutil.copy2(path, out)
    marker = {"schema": 1, "owner": owner, "skill": name, "name": aliases[name],
              "source": str(source.resolve()), "dependencies": dependency_paths,
              "linked_resources": used}
    write_json(destination / MARKER, marker)
    return marker


def view_snapshot(root: Path) -> dict[str, str]:
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        here = Path(current)
        for directory in list(directories):
            path = here / directory
            rel = path.relative_to(root)
            if path.is_symlink():
                result[rel.as_posix()] = "link:" + str(path.resolve())
                directories.remove(directory)
            elif not allowed(rel):
                directories.remove(directory)
        for name in files:
            path = here / name
            rel = path.relative_to(root)
            if rel.as_posix() == MARKER or not allowed(rel):
                continue
            # os.walk classifies a dangling directory link as a file. Retain its
            # identity so a registered legacy view can migrate after a source rename.
            result[rel.as_posix()] = ("link:" + str(path.resolve()) if path.is_symlink()
                                    else hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def safe_remove(path: Path, boundary: Path) -> None:
    """Remove only an explicitly bounded child; unlink links rather than following them."""
    path = Path(os.path.abspath(path))
    boundary = boundary.resolve()
    if path == boundary or not path.parent.resolve().is_relative_to(boundary):
        raise ValueError(f"Refusing removal outside {boundary}: {path}")
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        def writable(function, file, _):
            os.chmod(file, stat.S_IWRITE | stat.S_IREAD)
            function(file)
        shutil.rmtree(path, onerror=writable)
    elif path.exists():
        path.unlink()


def package(root: Path, output: Path) -> dict:
    summary = validate_repository(root)
    output = output.resolve()
    if output.is_relative_to((root / "skills").resolve()):
        raise ValueError("Archive output must be outside skills/")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [(Path("plugin.json"), root / "plugin.json")]
    files += [(Path(name), root / name) for name in generated_manifests(root)]
    files += [(Path(name), root / name) for name in
              ("README.md", "AGENTS.md", "skills.sh.json", "requirements-tools.txt",
               "scripts/manage_skills.py", "scripts/skill_repository.py", ".env.example") if (root / name).is_file()]
    files += [(path.relative_to(root), path) for path in (root / "spec").glob("*.md")]
    for name in SKILLS:
        files.extend((Path("skills") / name / rel, source)
                     for rel, source in skill_files(root / "skills" / name))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel, source in sorted(files, key=lambda pair: pair[0].as_posix()):
            archive.write(source, (Path(PLUGIN) / rel).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity check failed")
        if any(not allowed(Path(name)) for name in archive.namelist()):
            raise ValueError("Archive contains excluded paths")
    return dict(summary, archive=str(output), files=len(files),
                archive_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
