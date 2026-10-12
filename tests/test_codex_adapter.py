"""Codex-native packaging, coordinator, and lifecycle-hook contract.

These tests deliberately exercise public seams: the generated plugin archive, the
ask skill Codex loads, and hook stdin/stdout.  They do not claim per-role tool or
model isolation; Codex currently supplies one tool set to the native agent tree.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_pack():
    spec = importlib.util.spec_from_file_location("pack_team_codex", ROOT / "scripts/pack-team.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_pack()


class CodexPackageTest(unittest.TestCase):
    def test_antigravity_has_a_separate_portable_tree_without_codex_hooks(self):
        _, main = pack.unified_payload()
        _, antigravity = pack.antigravity_payload()
        self.assertIn("plugin.json", antigravity)
        self.assertIn("plugin.json", main)
        self.assertNotIn(".codex-plugin/plugin.json", antigravity)
        self.assertFalse(any(name.startswith("codex-hooks/") for name in antigravity))
        self.assertEqual(main["skills/ask/SKILL.md"], antigravity["skills/ask/SKILL.md"])
        self.assertNotIn("extensions", json.loads(antigravity["plugin.json"]))
        self.assertIn("Antigravity", json.loads(antigravity["plugin.json"])["description"])
        self.assertEqual(antigravity, pack.payload_for_host("antigravity")[1])

    def test_archive_plan_uses_the_selected_host_without_building(self):
        with tempfile.TemporaryDirectory() as directory:
            main_path, main_version, main = pack.archive_plan(directory, host="main")
            ag_path, ag_version, antigravity = pack.archive_plan(directory, host="antigravity")
            self.assertEqual(main_version, ag_version)
            self.assertTrue(main_path.name.endswith("-team.plugin"))
            self.assertTrue(ag_path.name.endswith("-antigravity.plugin"))
            self.assertIn(".codex-plugin/plugin.json", main)
            self.assertNotIn(".codex-plugin/plugin.json", antigravity)
            self.assertFalse(main_path.exists() or ag_path.exists(), "planning must not build an archive")

    def test_non_codex_generated_changes_are_explicitly_allowlisted(self):
        _, entries = pack.unified_payload()
        intentional = {
            ".claude-plugin/plugin.json", ".cursor-plugin/plugin.json", "plugin.json", "HOST-NOTES.md",
            "skills/ask/SKILL.md", "knowledge/skills/workflow/ask/SKILL.md",
            "agents/verify.md", "knowledge/agents/verify.md",  # remove inherited trailing whitespace
        }
        tree = ROOT / "plugins/shode-house"
        previous = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "plugins/shode-house"],
            text=True, capture_output=True, check=True, cwd=ROOT,
        ).stdout.splitlines()
        for full_name in previous:
            name = full_name.removeprefix("plugins/shode-house/")
            if name in intentional or name.startswith(".codex-plugin/"):
                continue
            old = subprocess.run(
                ["git", "show", f"HEAD:{full_name}"], capture_output=True, check=True, cwd=ROOT,
            ).stdout
            self.assertEqual(old, entries[name], name)

    def test_codex_manifest_registers_onboarding_and_trusted_hook_bundle_only_for_codex(self):
        _, entries = pack.unified_payload()
        codex = json.loads(entries[".codex-plugin/plugin.json"])
        claude = json.loads(entries[".claude-plugin/plugin.json"])

        self.assertEqual("./skills/ask/SKILL.md", codex["extensions"]["com.openai"]["onboardingSkill"])
        self.assertEqual("./codex-hooks/hooks.json", codex["hooks"])
        self.assertNotIn("skills-only", codex["description"])
        self.assertIn("Codex", codex["description"])
        self.assertNotIn("hooks", claude)
        self.assertNotIn("extensions", claude)
        portable = json.loads(entries["plugin.json"])
        openai = portable["extensions"]["com.openai"]
        self.assertEqual("./codex-hooks/hooks.json", openai["hooks"])
        self.assertEqual("./skills/ask/SKILL.md", openai["onboardingSkill"])
        self.assertNotIn("hooks/hooks.json", entries)  # would be auto-discovered by Claude too
        for name in ("codex-hooks/hooks.json", "codex-hooks/session_context.py",
                     "codex-hooks/pre_tool_use.py"):
            self.assertIn(name, entries)

    def test_codex_hooks_cover_start_compaction_subagents_and_supported_mutations(self):
        _, entries = pack.unified_payload()
        hooks = json.loads(entries["codex-hooks/hooks.json"])["hooks"]
        self.assertIn("startup|resume|clear|compact", hooks["SessionStart"][0]["matcher"])
        self.assertIn("SubagentStart", hooks)
        self.assertRegex(hooks["PreToolUse"][0]["matcher"], r"apply_patch")
        commands = json.dumps(hooks)
        self.assertIn("${PLUGIN_ROOT}/codex-hooks/session_context.py", commands)
        self.assertIn("${PLUGIN_ROOT}/codex-hooks/pre_tool_use.py", commands)
        self.assertIn("%PLUGIN_ROOT%\\\\codex-hooks\\\\session_context.py", commands)
        self.assertIn("%PLUGIN_ROOT%\\\\codex-hooks\\\\pre_tool_use.py", commands)

    def test_ask_is_a_real_codex_coordinator_when_native_delegation_exists(self):
        _, entries = pack.unified_payload()
        ask = entries["skills/ask/SKILL.md"].decode()
        self.assertNotIn("team execution needs the router style (Claude Code)", ask)
        self.assertIn("genuine separate-worker delegation", ask)
        self.assertIn("one axis per fresh worker", ask)
        self.assertIn("SHODE_CODEX_HOOKS=ACTIVE", ask)
        self.assertIn("ADVISORY-ONLY", ask)
        for role in ("plan", "build", "verify", "operate", "secure", "design"):
            self.assertIn(f"`{role}`", ask)
        self.assertRegex(ask, r"standards, spec, runtime,\s*security, domain and UI")


class CodexHookRuntimeTest(unittest.TestCase):
    def run_hook(self, script, payload, cwd=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "release/hosts/codex/hooks" / script)],
            input=json.dumps(payload), text=True, capture_output=True, cwd=cwd or ROOT,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT)}, timeout=10,
        )

    def test_session_context_restores_router_contract_after_compaction(self):
        result = self.run_hook("session_context.py", {
            "hook_event_name": "SessionStart", "source": "compact", "cwd": str(ROOT),
            "permission_mode": "default",
        })
        self.assertEqual(0, result.returncode, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual("SessionStart", body["hookSpecificOutput"]["hookEventName"])
        context = body["hookSpecificOutput"]["additionalContext"]
        self.assertIn("SHODE_CODEX_HOOKS=ACTIVE", context)
        self.assertIn("not an authentication signal", context)
        self.assertIn("shode-house:ask", context)
        self.assertIn("compaction", context.lower())

    def test_pre_tool_hook_denies_control_plane_and_git_patch_targets(self):
        for target in (".git/hooks/pre-commit", "safe/../.git/config", "src/bad\u009bname.py", "src/bad\u202ename.py",
                       ".shode-house/x/../state/current.json", ".shode-house/state/current.json",
                       ".shode-house/journal/a.jsonl", ".shode-house/scope/task.json"):
            patch = f"*** Begin Patch\n*** Add File: {target}\n+x\n*** End Patch\n"
            result = self.run_hook("pre_tool_use.py", {
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {"command": patch}, "cwd": str(ROOT),
            })
            self.assertEqual(2, result.returncode, (target, result.stdout, result.stderr))
            self.assertIn("DENY", result.stderr)

        direct = self.run_hook("pre_tool_use.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/bad\u0085name.py"}, "cwd": str(ROOT),
        })
        self.assertEqual(2, direct.returncode, direct.stderr)
        for destination in (".git/config", ".shode-house/state/current.json", "src/bad\u009bname.py"):
            moved = self.run_hook("pre_tool_use.py", {
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Update File: src/good.py\n"
                                          f"*** Move to: {destination}\n@@\n-x\n+y\n*** End Patch\n"},
                "cwd": str(ROOT),
            })
            self.assertEqual(2, moved.returncode, (destination, moved.stderr))

    def test_pre_tool_hook_denies_symlink_alias_into_protected_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / "alias").symlink_to(root / ".git", target_is_directory=True)
            result = self.run_hook("pre_tool_use.py", {
                "hook_event_name": "PreToolUse", "tool_name": "Write",
                "tool_input": {"file_path": "alias/config"}, "cwd": str(root),
            }, cwd=root)
        self.assertEqual(2, result.returncode, result.stderr)

    def test_pre_tool_hook_denies_hard_link_with_an_unknowable_peer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            protected = root / ".git/config"
            protected.write_text("keep\n")
            os.link(protected, root / "alias")
            result = self.run_hook("pre_tool_use.py", {
                "hook_event_name": "PreToolUse", "tool_name": "Edit",
                "tool_input": {"file_path": "alias"}, "cwd": str(root),
            }, cwd=root)
        self.assertEqual(2, result.returncode, result.stderr)

    def test_pre_tool_hook_allows_ordinary_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            patch = "*** Begin Patch\n*** Add File: src/example.py\n+x = 1\n*** End Patch\n"
            allowed = self.run_hook("pre_tool_use.py", {
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {"command": patch}, "cwd": directory,
            }, cwd=directory)
        self.assertEqual(0, allowed.returncode, allowed.stderr)

    def test_pre_tool_hook_denies_malformed_input(self):
        malformed = subprocess.run(
            [sys.executable, str(ROOT / "release/hosts/codex/hooks/pre_tool_use.py")],
            input="{", text=True, capture_output=True, cwd=ROOT, timeout=10,
        )
        self.assertEqual(2, malformed.returncode)


if __name__ == "__main__":
    unittest.main()
