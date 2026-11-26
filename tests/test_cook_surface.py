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
import tempfile
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

    def test_cook_is_the_only_registered_skill_and_the_rest_are_files(self):
        # 4.2.1: `cook` is the only registered skill in every generated tree; the other 19 ship under
        # knowledge/ and every agent, the router style and cook name how to Read them.
        source = {p.parent.name: p.relative_to(ROOT).as_posix()
                  for b in pack.BUCKETS for p in (ROOT / "skills" / b).glob("*/SKILL.md")}
        self.assertEqual(20, len(source))
        for host, entries in self.trees.items():
            with self.subTest(host=host):
                flat = {Path(p).parent.name for p in entries if re.fullmatch(r"skills/[^/]+/SKILL\.md", p)}
                self.assertEqual({"cook"}, flat)
                for name, rel in source.items():
                    self.assertIn("knowledge/" + rel, entries, name)
                line = pack.file_skills_line(pack.collect()[1])
                for name in set(source) - {"cook"}:
                    self.assertIn(name, line)
                carriers = [p for p in entries if re.fullmatch(r"agents/[^/]+\.md|output-styles/[^/]+\.md", p)]
                carriers.append("skills/cook/SKILL.md")
                self.assertEqual(8, len(carriers))
                for path in carriers:
                    self.assertIn(line, entries[path].decode(), path)

    def test_every_loaded_skill_and_agent_preload_resolves_to_a_shipped_file(self):
        # A skill named as `shode-house:<name>` in a generated agent, the router style or cook is either an agent
        # type (still native) or a skill whose knowledge/ SKILL.md ships; each agent reads its former preloads.
        source = {p.parent.name: p.relative_to(ROOT).as_posix()
                  for b in pack.BUCKETS for p in (ROOT / "skills" / b).glob("*/SKILL.md")}
        for host, entries in self.trees.items():
            cook = entries["skills/cook/SKILL.md"].decode()
            for name in WORKFLOWS:   # the router's table links each workflow to its shipped knowledge/ file
                link = f"](../../knowledge/references/workflows/{name}.md)"
                self.assertIn(link, cook, (host, name))
                self.assertIn(f"knowledge/references/workflows/{name}.md", entries, (host, name))
            for path in [p for p in entries if re.fullmatch(r"agents/[^/]+\.md|output-styles/[^/]+\.md", p)
                         ] + ["skills/cook/SKILL.md"] + [f"knowledge/references/workflows/{n}.md" for n in WORKFLOWS]:
                text = entries[path].decode()
                with self.subTest(host=host, path=path):
                    for name in set(re.findall(r"shode-house:([a-z][a-z0-9-]*)", text)):
                        if name in pack.ROLES or name == "cook":
                            continue
                        self.assertIn(name, source, f"{path} loads an unknown skill shode-house:{name}")
                        self.assertIn("knowledge/" + source[name], entries)
                    if path.startswith("agents/"):
                        for name in pack.preload_names(text, path):
                            self.assertIn(pack.PLUGIN_ROOT + "knowledge/" + source[name], text)

    def test_cook_skill_floor_and_footer_are_the_generated_ones(self):
        for host, entries in self.trees.items():
            with self.subTest(host=host):
                text = entries["skills/cook/SKILL.md"].decode()
                self.assertTrue(text.startswith("---\nname: cook\n"))
                block = pack.style_floor_block(pack.collect()[1])
                self.assertEqual("\n\n" + block, text.split("---", 2)[2][:2 + len(block)])
                # 4.2.1: the authority line, then (after a blank line) the generated file-skills paragraph
                self.assertTrue(text.endswith(pack.AUTHORITY_ENTRY + "\n" + pack.file_skills_line(pack.collect()[1])))

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

    def test_arguments_definition_strips_the_intent_word_and_the_workflows_agree(self):
        cook = (ROOT / "skills/workflow/cook/SKILL.md").read_text()
        self.assertEqual(1, cook.count("$ARGUMENTS"))   # only the deliberate substitution line
        self.assertIn("\nUser request: $ARGUMENTS\n", cook)
        self.assertIn("`ARGUMENTS` (written with a leading dollar sign inside the workflow files) = the\nuser's request with the leading intent word", cook)
        self.assertIn("every flag kept", cook)
        self.assertIn('`cook init --quick "x"` gives `--quick "x"`', cook)
        self.assertIn("`cook review KJERP-402` gives `KJERP-402`", cook)
        self.assertIn("prompt-level rule", cook)

    @staticmethod
    def bash_block(workflow, marker):
        text = (ROOT / f"references/workflows/{workflow}.md").read_text()
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            if marker in block:
                return block
        raise AssertionError(f"no bash block with {marker!r} in {workflow}")

    def run_bash(self, script, cwd=None):
        return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

    def test_init_mode_detection_runs_quick_for_the_stripped_arguments(self):
        block = self.bash_block("init", "MODE=")
        for args, mode, stack in (
            ('--quick "go api"', "quick", '"go api"'),
            ("", "interactive", ""),
            ("my-project", "interactive", ""),
        ):
            with self.subTest(arguments=args):
                out = self.run_bash(f'ARGUMENTS=\'{args}\'\n{block}\necho "$MODE|$STACK"')
                self.assertEqual(f"{mode}|{stack}", out)

    def test_review_debt_and_target_checks_match_the_stripped_arguments(self):
        review = (ROOT / "references/workflows/review.md").read_text()
        self.assertIn("ถ้า `$ARGUMENTS` = `--debt`", review)           # `cook review --debt` gives exactly `--debt`
        self.assertIn('getJiraIssue(issueIdOrKey="$ARGUMENTS")', review)  # `cook review KJERP-402` gives only the key

    def test_init_brownfield_guard_treats_any_existing_content_as_brownfield(self):
        block = self.bash_block("init", "PROJECT=")

        def dangling_link(d):
            (d / ".git").symlink_to(d / "no-such-target")

        def source_only(d):
            (d / "app.py").write_text("print(1)\n")
            (d / "src").mkdir()

        cases = {
            "fresh": (lambda d: None, "fresh"),
            "git-dir": (lambda d: (d / ".git").mkdir(), "brownfield"),
            "git-file-worktree": (lambda d: (d / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n"), "brownfield"),
            "git-dangling-symlink": (dangling_link, "brownfield"),
            "manifest-only": (lambda d: (d / "package.json").write_text("{}"), "brownfield"),
            "source-only": (source_only, "brownfield"),
            "dotfile-only": (lambda d: (d / ".env.example").write_text("A=1\n"), "brownfield"),
        }
        for name, (setup, expected) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                setup(Path(tmp))
                self.assertEqual(expected, self.run_bash(f'{block}\necho "$PROJECT"', cwd=tmp))

    def test_moved_workflows_carry_no_stale_command_wording(self):
        for name in WORKFLOWS:
            text = (ROOT / f"references/workflows/{name}.md").read_text()
            for stale in ("allowed-tools", "alias เก่า", "/automate-test", "Command นี้", "command นี้"):
                self.assertNotIn(stale, text, f"{name}: {stale}")


if __name__ == "__main__":
    unittest.main()
