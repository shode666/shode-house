"""4.2.0 single-entry surface: `cook` is the only public entry (shode-house-wy5).

Complements tests/test_cook_acceptance.py (the externally owned structural acceptance, never edited here) with what it
does not cover: the Antigravity tree, every manifest value, the source plugin, the route table of cook's router,
the Codex capability gate and the SessionStart text. No behavioural routing is claimed; that stays BLOCKED until a
real host run is recorded.
"""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("consult", "init", "spec", "implement", "review")
FAIL_CLOSED = "`BLOCKED: team execution needs the router style (Claude Code)`"


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load("pack_team_cook_surface", "scripts/pack-team.py")


def named_ask(path):
    parts = Path(path).parts
    return "ask" in parts or Path(parts[-1]).stem == "ask"   # tombstone-allow


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


class CookSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trees = {"main": pack.unified_payload()[1], "antigravity": pack.antigravity_payload()[1]}

    def test_no_tree_path_is_named_ask_and_no_tree_ships_a_command(self):
        for host, entries in self.trees.items():
            with self.subTest(host=host):
                self.assertEqual([], [p for p in entries if named_ask(p)])
                self.assertEqual([], [p for p in entries if p.startswith(("commands/", "knowledge/commands/"))])
                flat = {Path(p).parent.name for p in entries if re.fullmatch(r"skills/[^/]+/SKILL\.md", p)}
                source = {p.parent.name for b in pack.BUCKETS for p in (ROOT / "skills" / b).glob("*/SKILL.md")}
                self.assertEqual(source, flat)
                self.assertEqual(20, len(flat))
                self.assertIn("cook", flat)

    def test_cook_skill_floor_and_footer_are_the_generated_ones(self):
        for host, entries in self.trees.items():
            with self.subTest(host=host):
                text = entries["skills/cook/SKILL.md"].decode()
                self.assertTrue(text.startswith("---\nname: cook\n"))
                block = pack.style_floor_block(pack.collect()[1])
                self.assertEqual("\n\n" + block, text.split("---", 2)[2][:2 + len(block)])
                self.assertTrue(text.endswith(pack.AUTHORITY_ENTRY))

    def test_no_manifest_value_names_ask_and_no_manifest_registers_a_command(self):
        manifests = [ROOT / ".claude-plugin/plugin.json", ROOT / ".claude-plugin/marketplace.json"]
        for host, entries in self.trees.items():
            for name in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "plugin.json"):
                if name in entries:
                    data = json.loads(entries[name])
                    self.assertTrue(all(not re.search(r"(^|[^A-Za-z])ask([^A-Za-z]|$)", v) for v in strings(data)),
                                    f"{host}:{name}")
                    self.assertEqual([], data.get("commands", []), f"{host}:{name}")
        for path in manifests:
            data = json.loads(path.read_text())
            self.assertTrue(all(not re.search(r"(^|[^A-Za-z])ask([^A-Za-z]|$)", v) for v in strings(data)), str(path))
            self.assertNotIn("commands", data)
        for name in (".codex-plugin/plugin.json", "plugin.json"):
            onboarding = json.loads(self.trees["main"][name])["extensions"]["com.openai"]["onboardingSkill"]
            self.assertEqual("./skills/cook/SKILL.md", onboarding)

    def test_source_plugin_has_no_commands_dir_no_allowlist_entry_and_no_ask_skill(self):
        self.assertFalse((ROOT / "commands").exists())
        allow = [l.strip() for l in (ROOT / ".pack-allowlist").read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
        self.assertNotIn("commands", allow)
        self.assertEqual([], [p for p in (ROOT / "skills").glob("*/ask")])   # tombstone-allow
        self.assertTrue((ROOT / "skills/workflow/cook/SKILL.md").is_file())

    def test_router_selects_each_workflow_by_a_markdown_link_that_exists_in_every_shape(self):
        cook = (ROOT / "skills/workflow/cook/SKILL.md").read_text()
        self.assertIn("## Workflow selection", cook)
        for name in WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertIn(f"](../../../references/workflows/{name}.md)", cook)
                self.assertTrue((ROOT / f"references/workflows/{name}.md").is_file())
                for host, entries in self.trees.items():
                    self.assertIn(f"knowledge/references/workflows/{name}.md", entries, host)
        for token in ("--quick", "--stop", "--estimate", "--debt", "read-only", "brownfield", "interactive", "resume"):
            self.assertIn(token, cook.lower() + " ".join(
                (ROOT / f"references/workflows/{n}.md").read_text().lower() for n in WORKFLOWS))
        # the tree copy of the router links the same workflow files, resolved inside the tree
        tree_cook = self.trees["main"]["skills/cook/SKILL.md"].decode()
        for name in WORKFLOWS:
            self.assertIn(f"](../../knowledge/references/workflows/{name}.md)", tree_cook)

    def test_no_other_tree_file_repeats_the_router_headings(self):
        headings = ("## Fast path or full workflow (single owner)", "## Dispatch real specialists",
                    "## Efficient, durable work", "## Team orientation", "## Workflow selection")
        for host, entries in self.trees.items():
            for path, body in entries.items():
                if not path.endswith(".md") or path.endswith("/cook/SKILL.md"):
                    continue
                text = body.decode("utf-8", "replace")
                for heading in headings:
                    self.assertNotIn("\n" + heading + "\n", text, f"{host}:{path}")

    def test_codex_capability_gate_cook_never_carries_the_fail_closed_literal(self):
        cook = (ROOT / "skills/workflow/cook/SKILL.md").read_text()
        self.assertNotIn(FAIL_CLOSED, cook)
        self.assertNotIn("BLOCKED: team execution needs the router style", cook)
        for name in WORKFLOWS:
            text = (ROOT / f"references/workflows/{name}.md").read_text()
            self.assertLessEqual(len([l for l in text.splitlines() if l.startswith("Router style")]), 1, name)
        for name in ("consult", "spec", "implement", "review"):   # init carries no style gate of its own
            text = (ROOT / f"references/workflows/{name}.md").read_text()
            self.assertEqual(1, len([l for l in text.splitlines() if l.startswith("Router style not active")]), name)

    def test_codex_session_context_names_cook_only(self):
        for event in ("SessionStart", "SubagentStart"):
            out = subprocess.run([sys.executable, str(ROOT / "release/hosts/codex/hooks/session_context.py")],
                                 input=json.dumps({"hook_event_name": event, "source": "compact"}),
                                 capture_output=True, text=True, check=True).stdout
            context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("shode-house:cook", context)
            self.assertNotIn("shode-house:ask", context)   # tombstone-allow
            if event == "SessionStart":
                self.assertIn("reload the cook router contract", context)

    def test_collision_scan_names_the_flat_layout_skills_and_reserves_them_for_commands(self):
        scan = load("collision_scan_cook_surface", "hooks/scripts/collision-scan.py")
        skills, commands, _ = scan.shipped_names(str(ROOT / "plugins/shode-house"))
        self.assertIn("cook", skills)
        self.assertEqual(set(), commands)
        source_skills, _, _ = scan.shipped_names(str(ROOT))
        self.assertIn("cook", source_skills)
        self.assertNotIn("ask", skills | source_skills)   # tombstone-allow


if __name__ == "__main__":
    unittest.main()
