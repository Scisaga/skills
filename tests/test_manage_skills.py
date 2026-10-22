"""Behavioral installation tests; no real client configuration or network access."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import manage_skills as cli
import skill_repository as repo


def fixture(root):
    root.mkdir()
    repo.write_json(root / "plugin.json", repo.read_json(repo.ROOT / "plugin.json"))
    for name in repo.SKILLS:
        directory = root / "skills" / name
        (directory / "agents").mkdir(parents=True)
        (directory / "assets").mkdir()
        (directory / "scripts").mkdir()
        (directory / "references").mkdir()
        body = f"---\nname: {name}\ndescription: Use this skill for {name}.\n---\nUse ${name}.\nbash skills/{name}/scripts/run.sh\n"
        if name == "video":
            body += "[ASR](../speech/references/asr.md)\n"
        (directory / "SKILL.md").write_text(body, encoding="utf-8")
        (directory / "agents/openai.yaml").write_text(
            "interface:\n  icon_small: ./assets/logo.svg\n  icon_large: ./assets/logo.svg\n"
            f"  brand_color: '#123456'\n  default_prompt: Use ${name}.\n", encoding="utf-8")
        (directory / "assets/logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        (directory / "scripts/run.sh").write_text("echo fixture\n", encoding="utf-8")
        (directory / "references/asr.md").write_text("ASR instructions\n", encoding="utf-8")
    repo.sync_manifests(root)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="scisaga-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        fixture(self.root)
        self.home, self.state = self.base / "home", self.base / "state"
        self.manager = cli.Manager(self.state, self.home)
        self.source = cli.load_source(str(self.root), "main", self.state, self.manager.runner)

    def install(self, selected=None, aliases=None):
        return self.manager.standalone("codex", self.source, selected, aliases or {}, copy=True)

    def test_alias_dependency_and_paths_work_outside_repository(self):
        self.install(["video"], {"speech": "my-voice"})
        target = self.home / ".agents/skills/ss-video"
        metadata = repo.read_json(target / repo.MARKER)
        self.assertEqual(metadata["dependencies"]["speech"], str(target.parent / "my-voice"))
        text = (target / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: ss-video", text)
        self.assertIn("$ss-video", text)
        self.assertIn(target.as_posix() + "/scripts/run.sh", text)
        self.assertTrue((target / "../my-voice/references/asr.md").is_file())
        self.assertIn("../my-voice/references/asr.md", text)
        self.assertIn("$my-voice", (target.parent / "my-voice/agents/openai.yaml").read_text())
        ui = repo.yaml_module().safe_load((target.parent / "my-voice/agents/openai.yaml").read_text())["interface"]
        self.assertEqual(ui["display_name"], "my-voice")

    def test_foreign_registered_name_is_checked_even_when_folder_differs(self):
        foreign = self.home / ".codex/skills/.system/unrelated-folder"
        foreign.mkdir(parents=True)
        manifest = foreign / "SKILL.md"
        manifest.write_text("---\nname: ss-slides\ndescription: foreign\nlicense: MIT\n---\nuntouched")
        before = manifest.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "冲突"):
            self.install(["slides"])
        self.install(["slides"], {"slides": "my-slides"})
        self.assertEqual(before, manifest.read_bytes())

    def test_installed_document_commands_handle_spaces_outside_repository(self):
        self.manager = cli.Manager(self.state, self.base / "home with spaces")
        self.install(["slides"])
        target = Path(self.manager.records()[0]["target"])
        command = next(line for line in (target / "SKILL.md").read_text().splitlines() if line.startswith("bash "))
        bash = shutil.which("bash")
        if os.name == "nt" and Path("C:/Program Files/Git/bin/bash.exe").is_file():
            bash = "C:/Program Files/Git/bin/bash.exe"
        if not bash:
            self.skipTest("Bash unavailable")
        output = self.manager.runner.run([bash, "-c", command], cwd=self.base)
        self.assertEqual(output, "fixture")

    def test_two_sources_coexist_and_aliases_survive_updates(self):
        self.install(["video"], {"speech": "my-voice"})
        second = self.base / "source-two"
        shutil.copytree(self.root, second)
        other = cli.load_source(str(second), "main", self.state, self.manager.runner)
        self.manager.standalone("codex", other, ["video"], {"video": "another-video", "speech": "another-voice"}, True)
        self.manager.update("codex", "standalone")
        names = {entry["name"] for entry in self.manager.records()}
        self.assertEqual(names, {"ss-video", "my-voice", "another-video", "another-voice"})
        self.assertTrue(all(self.manager.usable(entry) for entry in self.manager.records()))

    def test_named_update_and_uninstall_only_affect_the_selected_source(self):
        self.install(["video"], {"speech": "my-voice"})
        other_root = self.base / "another-source"
        shutil.copytree(self.root, other_root)
        other = cli.load_source(str(other_root), "main", self.state, self.manager.runner)
        self.manager.standalone("codex", other, ["video"], {"video": "other-video", "speech": "other-voice"}, True)
        manifest = repo.read_json(self.root / "plugin.json")
        manifest["version"] = "0.1.1"
        repo.write_json(self.root / "plugin.json", manifest)
        repo.sync_manifests(self.root)
        self.manager.update("codex", "standalone", names=["ss-video"])
        self.assertEqual({entry["name"]: entry["version"] for entry in self.manager.records()},
                         {"ss-video": "0.1.1", "my-voice": "0.1.1", "other-video": "0.1.0", "other-voice": "0.1.0"})
        self.manager.uninstall("codex", "standalone", None, ["other-video"])
        self.manager.uninstall("codex", "standalone", None, ["other-voice"])
        self.assertEqual({entry["name"] for entry in self.manager.records()}, {"ss-video", "my-voice"})

    def test_expired_budget_during_view_creation_preserves_existing_install(self):
        self.install(["slides"])
        old = self.manager.records()[0].copy()
        render = repo.render_view
        def expire_after_render(*args, **kwargs):
            result = render(*args, **kwargs)
            self.manager.runner.deadline = time.monotonic() - 1
            return result
        with patch.object(cli, "render_view", side_effect=expire_after_render):
            with self.assertRaisesRegex(RuntimeError, "60 秒"):
                self.manager.update("codex", "standalone")
        self.assertTrue(self.manager.usable(old))
        self.assertEqual(self.manager.records()[0], old)

    def test_nested_config_runtime_and_notes_survive_update_uninstall_reinstall(self):
        self.install(["video"])
        targets = [Path(entry["target"]) for entry in self.manager.records()]
        for target in targets:
            for relative in (".env", "scripts/.env", ".venv/local-data", "my-notes.txt"):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("LOCAL-ONLY", encoding="utf-8")
        manifest = repo.read_json(self.root / "plugin.json")
        manifest["version"] = "0.1.1"
        repo.write_json(self.root / "plugin.json", manifest)
        repo.sync_manifests(self.root)
        self.manager.update("codex", "standalone", ["video"])
        for target in targets:
            self.assertEqual((target / "scripts/.env").read_text(), "LOCAL-ONLY")
        self.manager.uninstall("codex", "standalone", None)
        self.assertEqual(self.manager.records(), [])
        self.install(["video"])
        self.manager.uninstall("codex", "standalone", None)
        for target in targets:
            for relative in (".env", "scripts/.env", ".venv/local-data", "my-notes.txt"):
                self.assertEqual((target / relative).read_text(), "LOCAL-ONLY")
            self.assertFalse((target / "SKILL.md").exists())

    def test_dependency_cannot_be_uninstalled_while_used(self):
        self.install(["video"])
        with self.assertRaisesRegex(RuntimeError, "依赖"):
            self.manager.uninstall("codex", "standalone", ["speech"])
        self.assertEqual(len(self.manager.records()), 2)

    def test_video_is_unusable_when_its_registered_dependency_is_missing(self):
        self.install(["video"], {"speech": "my-voice"})
        video = next(entry for entry in self.manager.records() if entry["skill"] == "video")
        self.assertTrue(self.manager.usable(video))
        (self.home / ".agents/skills/my-voice/SKILL.md").unlink()
        self.assertFalse(self.manager.usable(video))

    def test_modified_managed_file_is_never_overwritten_or_uninstalled(self):
        self.install(["speech"])
        path = Path(self.manager.records()[0]["target"]) / "scripts/run.sh"
        path.write_text("local modification")
        with self.assertRaisesRegex(RuntimeError, "本地修改"):
            self.manager.update("codex", "standalone")
        with self.assertRaisesRegex(RuntimeError, "本地修改"):
            self.manager.uninstall("codex", "standalone", None)
        self.assertEqual(path.read_text(), "local modification")

    def test_known_unchanged_legacy_install_migrates_but_unknown_copy_remains(self):
        self.install(["slides"])
        entry = self.manager.records()[0]
        current = Path(entry["target"])
        legacy = current.parent / "build-narrated-presentation"
        current.rename(legacy)
        entry.update(skill=legacy.name, name=legacy.name, target=str(legacy))
        document = legacy / "SKILL.md"
        document.write_text(document.read_text().replace("name: ss-slides", "name: " + legacy.name))
        entry["snapshot"] = repo.view_snapshot(legacy)
        self.manager.save()
        self.manager.update("codex", "standalone")
        self.assertTrue(current.is_dir())
        self.assertFalse(legacy.exists())
        self.assertEqual(self.manager.records()[0]["name"], "ss-slides")
        unknown = current.parent / "android-termux-ssh"
        unknown.mkdir()
        (unknown / "SKILL.md").write_text("unknown local copy")
        self.install(["termux-ssh"])
        self.assertEqual((unknown / "SKILL.md").read_text(), "unknown local copy")

    def test_archive_is_installable_and_never_contains_local_configuration(self):
        for relative in (".env", "skills/speech/.env", "skills/speech/scripts/.env",
                         "skills/speech/.venv/key.txt", "skills/video/scripts/__pycache__/secret.pyc"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("SECRET-SENTINEL")
        archive_path = self.base / "release.zip"
        repo.package(self.root, archive_path)
        extracted = self.base / "unpacked"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertTrue(all(b"SECRET-SENTINEL" not in archive.read(name) for name in archive.namelist()))
            self.assertTrue(all(not (info.external_attr >> 16) & 0o120000 == 0o120000 for info in archive.infolist()))
            archive.extractall(extracted)
        clean_source = cli.load_source(str(extracted / "scisaga"), "main", self.state, self.manager.runner)
        self.manager.standalone("codex", clean_source, ["slides"], {}, True)
        self.assertTrue(self.manager.usable(self.manager.records()[0]))

    def test_gate_failure_reports_input_digest(self):
        (self.root / "skills/speech/assets/logo.svg").unlink()
        with self.assertRaisesRegex(ValueError, "input_sha256=[a-f0-9]{64}"):
            repo.validate_repository(self.root)

    def test_global_flags_work_on_both_sides_of_subcommand(self):
        for arguments in (["--home-dir", "fixture", "check"], ["check", "--home-dir", "fixture"]):
            self.assertEqual(cli.parser().parse_args(arguments).home_dir, Path("fixture"))

    @unittest.skipUnless(os.name == "nt", "Windows npm shim handling")
    def test_windows_npm_clients_run_declared_entries_without_shell_interpolation(self):
        for client, package, command in (("codex", "@openai/codex", "codex"), ("claude-code", "@anthropic-ai/claude-code", "claude")):
            modules = self.base / client / "node_modules"
            package_root = modules / package
            entry = package_root / "bin/client.js"
            entry.parent.mkdir(parents=True)
            entry.write_text("// fixture")
            repo.write_json(package_root / "package.json", {"bin": {command: "bin/client.js"}})
            shim = modules / ".bin" / (command + ".cmd")
            shim.parent.mkdir()
            shim.write_text("@echo off")
            with patch.object(cli.shutil, "which", side_effect=lambda name, shim=shim: "node.exe" if name == "node" else str(shim)):
                self.assertEqual(cli.client_command(client), ["node.exe", str(entry.resolve())])

    def test_launch_forwards_arguments_on_update_failure_with_usable_install(self):
        self.install(["slides"])
        forwarded = ["--", "--cd", "path with spaces", "prompt $() `literal`", "--help"]
        with patch.object(cli.Manager, "update", side_effect=RuntimeError("offline")), \
             patch.object(cli, "client_command", return_value=["fake-codex"]), \
             patch.object(cli.subprocess, "call", return_value=7) as call:
            result = cli.main(["--state-dir", str(self.state), "--home-dir", str(self.home), "launch", "codex", *forwarded])
        self.assertEqual(result, 7)
        self.assertEqual(call.call_args.args[0], ["fake-codex", *forwarded[1:]])

    def test_first_launch_without_usable_install_stops(self):
        with patch.object(cli, "client_command", return_value=["fake-codex"]), \
             patch.object(cli.subprocess, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "没有可用"):
                cli.main(["launch", "--state-dir", str(self.state), "--home-dir", str(self.home), "codex", "--", "--help"])
        call.assert_not_called()

    def test_native_namespace_owned_by_someone_else_is_never_mutated(self):
        with patch.object(self.manager, "native_inventory", return_value=([], [{"name": repo.MARKETPLACE, "root": "foreign"}])), \
             patch.object(self.manager, "native") as native:
            with self.assertRaisesRegex(RuntimeError, "未登记"):
                self.manager.plugin_install("codex", self.source)
        native.assert_not_called()

    def test_stale_native_cache_is_not_usable_without_active_registration(self):
        with patch.object(self.manager, "native_inventory", return_value=([], [])):
            self.assertFalse(self.manager.usable({"mode": "plugin", "agent": "codex", "version": "0.1.0"}))

    def test_owned_marketplace_allows_reinstall_after_managed_uninstall(self):
        market = {"name": repo.MARKETPLACE, "source": "directory", "path": "owned-catalog"}
        self.manager.registry["marketplaces"] = {"claude-code": {
            "source_identity": self.source["identity"], "native_marketplace": market}}
        with patch.object(self.manager, "native_inventory", return_value=([], [market])):
            self.manager.plugin_preflight("claude-code", [], self.source["identity"])
            with self.assertRaisesRegex(RuntimeError, "未登记"):
                self.manager.plugin_preflight("claude-code", [], "another-source")

    def test_claude_full_commit_uses_immutable_local_catalog_via_native_cli(self):
        source = dict(self.source, kind="git", url="https://example.invalid/skills.git", ref="a" * 40)
        active = {"id": f"{repo.PLUGIN}@{repo.MARKETPLACE}", "enabled": True, "version": "0.1.0"}
        market = {"name": repo.MARKETPLACE, "source": "directory", "path": "owned-catalog"}
        with patch.object(self.manager, "native_inventory", side_effect=[([], []), ([active], [market])]), \
             patch.object(self.manager, "native", return_value="installed") as native, \
             patch.object(self.manager, "find_plugin_cache", return_value=self.root):
            result = self.manager.plugin_install("claude-code", source)
        self.assertEqual(result["version"], "0.1.0")
        first = native.call_args_list[0].args
        self.assertEqual(first[:4], ("claude-code", "plugin", "marketplace", "add"))
        self.assertEqual(Path(first[4]), self.state / "marketplaces/claude-code")
        self.assertEqual(self.manager.records()[0]["source"]["ref"], "a" * 40)

    def test_runner_terminates_process_at_deadline(self):
        runner = cli.Runner(self.home, deadline=time.monotonic() + 0.1)
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "超时"):
            runner.run([sys.executable, "-c", "import time; time.sleep(10)"])
        self.assertLess(time.monotonic() - started, 5)

    def test_git_main_updates_pinned_commit_stays_and_modified_checkout_is_protected(self):
        runner = self.manager.runner
        runner.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.proxy", GIT_CONFIG_VALUE_0="",
                          NO_PROXY="127.0.0.1,localhost")
        def git(*arguments):
            return runner.run(["git", "-C", str(self.root), *arguments])
        def commit():
            git("add", ".")
            git("-c", "user.name=Scisaga Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
            return git("rev-parse", "HEAD")
        git("init", "-b", "main")
        first = commit()
        served = self.base / "served"
        served.mkdir()
        bare = served / "repository.git"
        runner.run(["git", "clone", "--bare", str(self.root), str(bare)])
        runner.run(["git", "--git-dir", str(bare), "update-server-info"])

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(served), **kwargs)
            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/repository.git"
        source = cli.load_source(url, "main", self.state, runner)
        self.manager.standalone("codex", source, ["slides"], {}, True)
        pinned = cli.load_source(url, first, self.state, runner)
        child = self.root / "extracted-source"
        fixture(child)
        nested = cli.load_source(str(child), "main", self.state, runner)
        self.assertEqual(nested["identity"], "local:" + str(child.resolve()))
        self.assertIsNone(nested["commit"])
        self.assertFalse(nested["dirty"])
        shutil.rmtree(child)
        manifest = repo.read_json(self.root / "plugin.json")
        manifest["version"] = "0.1.1"
        repo.write_json(self.root / "plugin.json", manifest)
        repo.sync_manifests(self.root)
        second = commit()
        git("push", str(bare), "main")
        runner.run(["git", "--git-dir", str(bare), "update-server-info"])
        self.manager.update("codex", "standalone")
        entry = self.manager.records()[0]
        self.assertEqual(entry["source"]["commit"], second)
        self.assertEqual(entry["version"], "0.1.1")
        still_pinned = cli.load_source(url, first, self.state, runner, pinned)
        self.assertEqual(still_pinned["commit"], first)
        (Path(entry["source"]["path"]) / "skills/slides/SKILL.md").write_text("local modification")
        with self.assertRaisesRegex(RuntimeError, "未提交修改"):
            self.manager.update("codex", "standalone")
        self.assertTrue(self.manager.usable(entry))


if __name__ == "__main__":
    unittest.main()
