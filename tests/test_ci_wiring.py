#!/usr/bin/env python3
"""CI workflow wiring outside gate #27's A15/W9 block (W10a, decision U21; bd v7u.4.7 notes).

- The workflow has three jobs (gate, suites, pack), each on the pinned runner with a timeout; `pack` needs both
  others and builds on a fresh runner where nothing has run before `make pack`; no gate text lives in the YAML
  (the gate step is `make validate` = scripts/ci-gate.sh, the suites step is `make suites`).
- Sentinel W1 follow-up F6: the workflow declares a top-level least-privilege `permissions:` block.
- Sentinel F6 / Chris W1 follow-up C-7: pytest is installed only from the hash-pinned .github/requirements-ci.txt
  (setup step and the in-gate venv fallback alike); every requirement is pinned with `==` and carries a hash.
- CI #21 (W5b note): anchors are read without `jq @tsv`, which doubled every backslash, so an anchor that holds
  a '\\' was always reported missing.
- CI #23 router owner form (v4 ADR §5.10, ledger W3 "CI #23 lazy-load OWNER"): `OWNER: router` resolves to the
  router style output-styles/<plugin>.md plus the skills it loads as `<plugin>:<skill>`. The 12 `OWNER:
  orchestrator` flips are shipped text and stay with the switch commit (W10b).
- CI #24a (Bella W10a S-1): a namespaced `<plugin>:<skill>` § Y section reference is checked, not skipped.
- CI #17 (U22 slice D): the design-intel smoke writes its payloads into a per-run `mktemp -d` under $TMPDIR that is
  removed on exit, never into fixed /tmp names (concurrent gates collided on /tmp/ds.json; fixed names are predictable).
- U22 iter 2: no pid-based (`$$`) temp name anywhere in the workflow or the gate script; the build step uses `mktemp` + an EXIT trap.
The #17, #21, #23 and #24 sections are cut out of scripts/ci-gate.sh together with the gate prelude and run with bash
in a scratch tree, so the real shell text is tested, not a copy of it.
Run: python3 tests/test_ci_wiring.py   (CI gate #27 runs it; stdlib + bash + jq)
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
GATE = ROOT / "scripts/ci-gate.sh"
MAKEFILE = ROOT / "Makefile"
ALLOWLIST = ROOT / ".pack-allowlist"
RUNNER = "ubuntu-26.04"
REQ = ROOT / ".github/requirements-ci.txt"
# The PATH every extracted gate section runs with; the bash/jq probe reads the same PATH, so a tool found only on
# the caller's PATH skips the test instead of failing it inside the gate run.
GATE_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"


class MaintenanceEvalWiringTest(unittest.TestCase):
    def test_maintenance_change_tests_are_in_make_validate_gate(self):
        text = GATE.read_text()
        self.assertIn("eval/maintenance-change/tests", text)
        self.assertRegex(text, r"for d in[^\n]*eval/maintenance-change/tests")


def gate_has(*tools):
    return all(shutil.which(tool, path=GATE_PATH) for tool in tools)


def gate_script():
    """The gate: scripts/ci-gate.sh from its first executable line (the header above it is comments + a root guard)."""
    lines = GATE.read_text().splitlines()
    return lines[lines.index("set +e -u -o pipefail"):]


def section(number):
    """Gate prelude (up to section 1) + section `number` up to the next section."""
    lines = gate_script()
    first = next(i for i, l in enumerate(lines) if l.startswith('sec "1. '))
    start = next(i for i, l in enumerate(lines) if l.startswith(f'sec "{number}. '))
    stop = next(i for i, l in enumerate(lines) if i > start and re.match(r'sec "\d', l))
    return "\n".join(lines[:first] + lines[start:stop]) + '\necho "fail=$fail"\n'


def sub24a():
    """Gate prelude + CI #24a only (the rest of #24 needs the whole repo)."""
    lines = gate_script()
    first = next(i for i, l in enumerate(lines) if l.startswith('sec "1. '))
    start = next(i for i, l in enumerate(lines) if l.startswith("# 24a. "))
    stop = next(i for i, l in enumerate(lines) if l.startswith("# 24b. "))
    return "\n".join(lines[:first] + lines[start:stop]) + '\necho "fail=$fail"\n'


def run_section(number, root):
    r = subprocess.run(["bash", "-c", section(number)], cwd=root, capture_output=True, text=True,
                       env={"PATH": GATE_PATH, "HOME": str(root)})
    return r.stdout + r.stderr


def tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


MANIFEST = json.dumps({"name": "shode-house", "version": "3.17.2", "skills": ["./skills/discipline/"]})


@unittest.skipUnless(gate_has("bash", "jq"), "needs bash + jq on the gate PATH")
class AnchorReadTest(unittest.TestCase):
    """CI #21: the anchor must reach grep -F byte for byte."""

    def run21(self, anchor, body):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rule = {"id": "r-backslash", "source_of_truth": "agents/a.md", "anchor": anchor}
            tree(root, {".claude-plugin/plugin.json": MANIFEST, "agents/a.md": body,
                        ".enforcement-map.json": json.dumps({"rules": [rule]})})
            return run_section(21, root)

    def test_anchor_with_a_backslash_is_found(self):
        anchor = r"never run `rm -rf \"$X\"` blind"
        out = self.run21(anchor, "# a\n- " + anchor + " here\n")
        self.assertNotIn("r-backslash' anchor", out, out)       # neither missing nor too short
        self.assertIn("rules -- inventory looks incomplete", out)  # the section ran to its end (1 rule < 15)

    def test_anchor_with_a_backslash_that_is_absent_is_red(self):
        anchor = r"match C:\temp\new only"
        out = self.run21(anchor, "# a\n- match C:\\\\temp\\\\new only (doubled, not the anchor)\n")
        self.assertIn("r-backslash' anchor 'match C:\\temp\\new only' ไม่พบใน agents/a.md", out)

    def test_anchor_with_a_tab_is_matched_exactly(self):
        anchor = "column one\tcolumn two"
        self.assertNotIn("r-backslash' anchor", self.run21(anchor, "# a\n" + anchor + "\n"))
        self.assertIn("ไม่พบใน agents/a.md", self.run21(anchor, "# a\ncolumn one column two\n"))

    def test_anchor_with_a_line_break_is_red(self):
        out = self.run21("first line of it\nsecond", "# a\nfirst line of it\nsecond\n")
        self.assertIn("rule 'r-backslash' มี field ที่มี line break หรือ U+001F", out)

    def test_no_tsv_read_of_anchors(self):
        sec21 = section(21)
        self.assertNotRegex(sec21, r"\.anchor[^\n]*@tsv")
        self.assertIn("IFS=$'\\x1f'", sec21)


@unittest.skipUnless(gate_has("bash", "jq"), "needs bash + jq on the gate PATH")
class RouterOwnerTest(unittest.TestCase):
    """CI #23: `OWNER: router` = the router style + the skill roots it loads."""

    LAZY = ("<!-- lazy-load-contract -->\nLOAD: skills/discipline/wf/detail.md\nWHEN: engagement start\n"
            "OWNER: {owner}\nREQUIRED-BEFORE: phase 1\n\n# detail\n")

    def run23(self, owner="router", style="Load `shode-house:wf` at engagement start.\n",
              skill="See detail.md for the steps.\n", agent=None, style_name="shode-house"):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            files = {".claude-plugin/plugin.json": MANIFEST,
                     "skills/discipline/wf/SKILL.md": "---\nname: wf\n---\n" + skill,
                     "skills/discipline/wf/detail.md": self.LAZY.format(owner=owner),
                     "agents/caller.md": "---\nname: caller\n---\nreads detail.md\n"}
            if style is not None:
                files[f"output-styles/{style_name}.md"] = "---\nname: shode-house\n---\n" + style
            if agent:
                files[f"agents/{owner}.md"] = agent
            tree(root, files)
            return run_section(23, root)

    def test_router_owner_reaches_through_a_skill_the_style_loads(self):
        out = self.run23()
        self.assertNotIn("detail.md: OWNER", out, out)
        self.assertNotIn("skills/discipline/wf/detail.md:", out, out)

    def test_router_owner_with_the_pointer_in_the_style_itself(self):
        out = self.run23(style="Read skills/discipline/wf/detail.md first.\n", skill="nothing here\n")
        self.assertNotIn("skills/discipline/wf/detail.md:", out, out)

    def test_router_owner_without_a_pointer_is_red(self):
        out = self.run23(style="No skill named here.\n")
        self.assertIn("detail.md: OWNER router ไม่มี pointer", out)

    def test_router_owner_without_the_router_style_is_red(self):
        self.assertIn("OWNER router แต่ไม่มี router style output-styles/shode-house.md", self.run23(style=None))
        self.assertIn("OWNER router แต่ไม่มี router style", self.run23(style_name="other"))

    def test_agent_owner_still_needs_the_agent_and_its_closure(self):
        out = self.run23(owner="ghost")
        self.assertIn("OWNER 'ghost' ไม่ใช่ agent ที่มีอยู่", out)
        ok = self.run23(owner="dev", agent='---\nname: dev\ntools: ["Read"]\nskills: ["wf"]\n---\n')
        self.assertNotIn("skills/discipline/wf/detail.md:", ok, ok)

    def test_orphan_check_applies_to_the_router_form_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            tree(root, {".claude-plugin/plugin.json": MANIFEST,
                        "skills/discipline/wf/SKILL.md": "---\nname: wf\n---\nnothing\n",
                        "skills/discipline/wf/detail.md": self.LAZY.format(owner="router"),
                        "output-styles/shode-house.md": "---\nname: s\n---\nRead skills/discipline/wf/detail.md\n"})
            out = run_section(23, root)
        # callers are counted in agents/ skills/ commands/ references/ for both forms; a pointer in the style alone
        # does not make a caller, so the router form keeps the orphan check
        self.assertIn("detail.md: ไม่มี caller อ้างถึงเลย (orphan lazy reference)", out)


@unittest.skipUnless(gate_has("bash", "jq"), "needs bash + jq on the gate PATH")
class NamespacedSectionRefTest(unittest.TestCase):
    """CI #24a (Bella W10a S-1, R41): a `<plugin>:<skill>` § Y reference is resolved like a bare skill name and its
    heading checked; before, the extraction regex had no ':' and skipped it silently."""

    def run24(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            tree(root, {".claude-plugin/plugin.json": MANIFEST,
                        "skills/discipline/wf/SKILL.md": "---\nname: wf\n---\n# wf\n\n## Postmortem template (blameless)\n",
                        "agents/a.md": "---\nname: a\n---\n" + "".join(l + "\n" for l in lines)})
            r = subprocess.run(["bash", "-c", sub24a()], cwd=root, capture_output=True, text=True,
                               env={"PATH": GATE_PATH, "HOME": str(root)})
            return r.stdout + r.stderr

    def test_namespaced_ref_with_a_real_heading_passes(self):
        out = self.run24(["Load `shode-house:wf` § Postmortem template (blameless) first.", "Bare `wf` § Postmortem template"])
        self.assertNotIn("agents/a.md:", out, out)

    def test_namespaced_ref_to_a_missing_heading_is_red(self):
        out = self.run24(["Load `shode-house:wf` § Incident timeline first."])
        self.assertRegex(out, r"X agents/a\.md: อ้าง 'wf § Incident timeline ?' แต่ไม่พบ heading นั้นใน skills/discipline/wf/SKILL\.md")

    def test_namespaced_ref_to_a_missing_skill_is_red(self):
        out = self.run24(["Load `shode-house:ghost` § Postmortem template first."])
        self.assertIn("X agents/a.md: อ้าง 'ghost § Postmortem templat' แต่หาไฟล์ 'ghost' ไม่เจอในรีโป", out)

    def test_other_namespace_or_a_path_after_the_namespace_is_red(self):
        out = self.run24(["Load `other-plugin:wf` § Postmortem template first."])
        self.assertIn("X agents/a.md: อ้าง 'other-plugin:wf § Postmortem templat' ด้วย namespace ที่ไม่ใช่ 'shode-house:'", out)
        out = self.run24(["Load `shode-house:wf/SKILL.md` § Postmortem template first."])
        self.assertIn("ไม่ใช่ชื่อ skill (<plugin>:<skill>)", out)

    def test_extraction_keeps_the_colon(self):
        self.assertIn("[A-Za-z0-9/_.:-]*", sub24a())
        self.assertIn("fail=0", self.run24(["nothing to check here"]))

def ci_jobs(text):
    """The jobs of a workflow as {name: body}. A top-level `jobs:` key and 2-space job keys; no YAML library needed."""
    body = text[text.index("\njobs:\n") + len("\njobs:\n"):]
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


# The `make suites` recipe, pinned (round-3 finding F1): the 11 suites in the order the old ci.yml steps ran them.
# Each is (title echoed, command). The eval-scorer block is long, so it is pinned by the sha256 of its logical line
# (continuations joined, whitespace collapsed); every other command is compared as text.
SCORER_SHA256 = "fe1c2bece73f09ffb1dd1a9fb1bc40536d716a965aadb49b8741ce597320f959"
SUITES = [
    ("per-run usage comparator", "python3 -m unittest discover -s tests -p 'test_usage_report.py'"),
    ("optional drain template contract (mock host, not live qualification)", "node --test tests/test_drain_template.mjs"),
    ("eval scorer smoke (committed recorded transcripts, no live agent run)", None),
    ("GS1 E2E regression gate (vs eval/baseline/e2e-golden/GS1-BASELINE.md)", "python3 scripts/eval-regression-gate.py"),
    ("workflow-state.sh", "bash tests/test-workflow-state.sh"),
    ("registry + route/policy-check", "bash tests/test-registry.sh"),
    ("scope-check", "bash tests/test-scope-check.sh"),
    ("permission-check", "bash tests/test-permission-check.sh"),
    ("reliability", "bash tests/test-reliability.sh"),
    ("hooks fixtures", "bash tests/test-hooks.sh"),
    ("lock primitive", "bash tests/test-lock.sh"),
]
# Any form that lets a failing suite pass: `|| true`, `|| :`, `; true`, `&& true`, a `-` recipe prefix, `set +e`.
SWALLOW = re.compile(r"\|\|\s*(?:true|:|exit\s+0)(?![\w])|[;&]\s*(?:true|:)\s*$|^[@+]*-|set\s+\+e|\|\|\s*$")


def suites_problems(makefile):
    """Everything wrong with the `make suites` recipe: the exact ordered 11 commands, nothing that swallows a failure."""
    problems = []
    if re.search(r"(?m)^\.(?:IGNORE|ONESHELL)\b", makefile):
        problems.append("the Makefile sets .IGNORE or .ONESHELL")
    head = re.search(r"(?m)^suites:(.*)$", makefile)
    if not head or head.group(1).strip():
        problems.append("the suites target is missing or has prerequisites")
    recipe = re.search(r"(?m)^suites:.*\n((?:\t.*\n)+)", makefile)
    if not recipe:
        return problems + ["no suites recipe"]
    logical, cur = [], ""
    for raw in recipe.group(1).splitlines():
        line = raw[1:]
        if line.endswith("\\"):
            cur += line[:-1] + " "
            continue
        logical.append(re.sub(r"\s+", " ", cur + line).strip())
        cur = ""
    want = len(SUITES) * 2
    if len(logical) != want:
        problems.append(f"the suites recipe has {len(logical)} commands, want {want} (11 echo + 11 suite)")
        return problems
    for i, (title, command) in enumerate(SUITES):
        echo, got = logical[2 * i], logical[2 * i + 1]
        if echo != f'@echo "== suite: {title} =="':
            problems.append(f"suite {i + 1} is not {title!r}, in this order")
        if command is None:
            if not got.startswith("@set -e; ") or hashlib.sha256(got.encode()).hexdigest() != SCORER_SHA256:
                problems.append(f"suite {i + 1} (eval scorer smoke) block changed")
        else:
            if got != command:
                problems.append(f"suite {i + 1} is not `{command}`")
            if SWALLOW.search(got):
                problems.append(f"suite {i + 1} swallows its exit code: {got}")
    return problems


def action_problems(text):
    """Every third-party `uses:` is a full 40-hex commit SHA with a `# vX.Y.Z` comment; every checkout drops its credentials."""
    problems = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", line)
        if m and not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1)):
            problems.append(f"uses: {m.group(1)} is not pinned to a 40-hex commit SHA")
        elif m and not re.fullmatch(r"\s+#\s+v\d+\.\d+\.\d+\s*", m.group(2)):
            problems.append(f"uses: {m.group(1)} has no `# vX.Y.Z` comment")
    steps = re.split(r"(?m)^(?=      - )", text)
    for step in steps:
        if re.match(r"      - uses: actions/checkout@", step) and not re.search(r"(?m)^          persist-credentials: false$", step):
            problems.append("an actions/checkout step lacks `persist-credentials: false`")
    return problems


def ci_problems(text, makefile):
    """Everything wrong with the shape of the workflow and the Makefile recipe it relies on (empty = right shape)."""
    problems = []
    live = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    jobs = ci_jobs(text)
    if sorted(jobs) != ["gate", "pack", "suites"]:
        return [f"jobs are {sorted(jobs)}, want gate, suites, pack"]
    if "ubuntu-latest" in live:
        problems.append("ubuntu-latest is used")
    for name, job in jobs.items():
        if not re.search(rf"(?m)^    runs-on: {re.escape(RUNNER)}$", job):
            problems.append(f"job {name} is not on {RUNNER}")
        if not re.search(r"(?m)^    timeout-minutes: [1-9]\d*$", job):
            problems.append(f"job {name} has no timeout-minutes")
    needs = re.search(r"(?m)^    needs: \[([^\]]*)\]$", jobs["pack"])
    if not needs or sorted(n.strip() for n in needs.group(1).split(",")) != ["gate", "suites"]:
        problems.append("pack does not need exactly [gate, suites]")
    for name in ("gate", "suites"):
        if re.search(r"(?m)^    needs:", jobs[name]):
            problems.append(f"job {name} must not wait for another job")
    if "        run: make validate\n" not in jobs["gate"] + "\n":
        problems.append("the gate job does not run `make validate`")
    if "        run: make suites\n" not in jobs["suites"] + "\n":
        problems.append("the suites job does not run `make suites`")
    if 'sec "' in text:
        problems.append("gate text (`sec \"`) is inlined in the workflow")
    for block in re.findall(r"(?ms)^ +run: \|\n(.*?)(?=^      - |\Z)", text):
        if len(block.rstrip().splitlines()) > 20:
            problems.append(f"a `run: |` block of {len(block.rstrip().splitlines())} lines (the gate/suites belong in scripts/Makefile)")
    # pack: a fresh runner, nothing but the checkout before the build step, nothing test-like before `make pack`
    pack = jobs["pack"]
    build = pack.index("      - name: Build .plugin artifact")
    before_step = re.findall(r"(?m)^      - (?:uses|name|run): (.*)$", pack[:build])
    if len(before_step) != 1 or not before_step[0].startswith("actions/checkout@"):
        problems.append(f"steps before the pack build step are {before_step}, want only the checkout")
    step = pack[build:]
    if "make pack" not in step:
        problems.append("the pack build step does not run make pack")
    else:
        head = "\n".join(l for l in step[:step.index("make pack")].splitlines() if not l.lstrip().startswith("#"))
        if re.search(r"make (validate|suites)|bash tests/|python3 tests/|tests/test", head):
            problems.append("something test-like runs before make pack in the pack job")
        if "umask 022" not in head:
            problems.append("no `umask 022` before make pack")
    problems += action_problems(text)
    problems += suites_problems(makefile)
    recipe = re.search(r"(?m)^validate:\n((?:\t.*\n)+)", makefile)
    if not recipe or recipe.group(1) != "\t@bash scripts/ci-gate.sh\n":
        problems.append("the Makefile validate recipe is not exactly `@bash scripts/ci-gate.sh`")
    return problems


class WorkflowShapeTest(unittest.TestCase):
    """Three jobs: `gate` and `suites` in parallel, then `pack` on a fresh runner; no gate text in the YAML."""

    @classmethod
    def setUpClass(cls):
        cls.text = CI.read_text(encoding="utf-8")
        cls.makefile = MAKEFILE.read_text(encoding="utf-8")

    def test_the_real_workflow_has_the_right_shape(self):
        self.assertEqual([], ci_problems(self.text, self.makefile))

    def test_the_gate_script_exists_and_is_not_shipped(self):
        self.assertTrue(GATE.is_file())
        entries = [l.split()[0] for l in ALLOWLIST.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertFalse("scripts/ci-gate.sh".startswith(entry.rstrip("/") + "/") or entry == "scripts/ci-gate.sh",
                                 "the gate script is maintainer-only and must not be in .pack-allowlist")

    def test_every_mutation_of_the_shape_is_red(self):
        t, m = self.text, self.makefile
        mutations = {
            "a job on ubuntu-latest": (t.replace(f"runs-on: {RUNNER}", "runs-on: ubuntu-latest", 1), m, "not on"),
            "a job without timeout": (t.replace("    timeout-minutes: 10\n", "", 1), m, "timeout-minutes"),
            "pack without suites": (t.replace("needs: [gate, suites]", "needs: [gate]"), m, "need exactly"),
            "pack without gate": (t.replace("needs: [gate, suites]", "needs: [suites]"), m, "need exactly"),
            "gate needs suites": (t.replace("  gate:\n", "  gate:\n    needs: [suites]\n", 1), m, "must not wait"),
            "a suite run before make pack": (t.replace("          make pack\n", "          bash tests/test-registry.sh\n          make pack\n", 1), m, "before make pack"),
            "make validate before make pack": (t.replace("          make pack\n", "          make validate\n          make pack\n", 1), m, "before make pack"),
            "no umask before make pack": (t.replace("          umask 022\n", ""), m, "umask"),
            "a step before the pack build": (t.replace("      - name: Build .plugin artifact", "      - run: make suites\n      - name: Build .plugin artifact"), m, "steps before"),
            "a gate command inlined": (t.replace("run: make validate", 'run: |\n          sec "1. x"'), m, "inlined"),
            "a long run block": (t.replace("run: make suites", "run: |\n" + "          echo x\n" * 30 + "          true"), m, "run: |"),
            "gate step no longer make validate": (t.replace("run: make validate", "run: bash scripts/ci-gate.sh"), m, "make validate"),
            "recipe changed": (t, m.replace("\t@bash scripts/ci-gate.sh\n", "\t@bash scripts/ci-gate.sh || true\n", 1), "recipe"),
            "a tag-only uses": (t.replace("actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0", "actions/setup-python@v5", 1), m, "40-hex"),
            "a uses without version comment": (t.replace(" # v4.6.2", "", 1), m, "comment"),
            "a checkout keeps credentials": (t.replace("          persist-credentials: false\n", "", 1), m, "persist-credentials"),
            "test-lock swallowed with || true": (t, m.replace("\tbash tests/test-lock.sh\n", "\tbash tests/test-lock.sh || true\n", 1), "swallows"),
            "test-lock swallowed with || :": (t, m.replace("\tbash tests/test-lock.sh\n", "\tbash tests/test-lock.sh || :\n", 1), "swallows"),
            "test-lock swallowed with ; true": (t, m.replace("\tbash tests/test-lock.sh\n", "\tbash tests/test-lock.sh; true\n", 1), "swallows"),
            "test-lock with a - prefix": (t, m.replace("\tbash tests/test-lock.sh\n", "\t-bash tests/test-lock.sh\n", 1), "swallows"),
            "a suite line dropped": (t, m.replace("\tbash tests/test-hooks.sh\n", "", 1), "commands, want"),
            "a suite command dropped, echo kept": (t, m.replace("\tbash tests/test-hooks.sh\n", "\t@true\n", 1), "suite 10"),
            "two suites reordered": (t, m.replace("\tbash tests/test-registry.sh\n", "\tbash tests/test-scope-check.sh\n", 1).replace("\tbash tests/test-scope-check.sh\n\t@echo \"== suite: permission", "\tbash tests/test-registry.sh\n\t@echo \"== suite: permission", 1), "suite"),
            "scorer block swallowed": (t, m.replace('exit 1; }\n\t@echo "== suite: GS1', 'exit 1; } || true\n\t@echo "== suite: GS1', 1), "scorer"),
            ".IGNORE set": (t, m + "\n.IGNORE:\n", "IGNORE"),
        }
        for label, (text, makefile, want) in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual((t, m), (text, makefile), "the mutation changed nothing")
                self.assertTrue(any(want in p for p in ci_problems(text, makefile)), (label, ci_problems(text, makefile)))


@unittest.skipUnless(gate_has("bash", "jq"), "needs bash + jq on the gate PATH")
class GateSectionTwoAndTimingTest(unittest.TestCase):
    """B10: CI #2 also fails when an excluded bucket (in-progress, deprecated) is listed in plugin.json `skills`.
    B6: every section reports its own time, the end lists the slowest."""

    def run2(self, skills):
        manifest = json.dumps({"name": "shode-house", "version": "3.17.2", "skills": skills})
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            tree(root, {".claude-plugin/plugin.json": manifest, "skills/discipline/a/SKILL.md": "x\n"})
            return run_section(2, root)

    def test_a_shipped_bucket_list_passes(self):
        out = self.run2(["./skills/discipline/", "./skills/workflow/"])
        self.assertIn("fail=0", out, out)

    def test_an_excluded_bucket_in_plugin_json_is_red(self):
        for bucket in ("in-progress", "deprecated"):
            with self.subTest(bucket=bucket):
                out = self.run2(["./skills/discipline/", f"./skills/{bucket}/"])
                self.assertIn(f"excluded bucket '{bucket}' is listed in plugin.json skills", out)
                self.assertIn("fail=1", out)

    def test_each_section_prints_its_time_and_the_end_lists_the_slowest(self):
        lines = gate_script()
        first = next(i for i, l in enumerate(lines) if l.startswith('sec "1. '))
        script = "\n".join(lines[:first]) + (
            '\nsec "a. quick"\nsec "b. slow"\nsleep 1\nsec "c. quick"\ntick; SECN=""\n'
            'printf "%s" "$TIMES" | sort -t"|" -k1,1nr | head -5\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            tree(root, {".claude-plugin/plugin.json": MANIFEST})
            r = subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True,
                               env={"PATH": GATE_PATH, "HOME": str(root)})
        out = r.stdout + r.stderr
        self.assertRegex(out, r"== b\. slow ==\n  \([1-9]\d*s\)\n", out)
        self.assertIn("== a. quick ==\n  (0s)\n", out)
        self.assertRegex(out, r"(?m)^[1-9]\d*\|b\. slow$")
        self.assertIn("== a. quick ==", out)   # the header list itself is unchanged by the timing lines
        self.assertNotRegex(out, r"(?m)^== .*\(\d+s\)")


class WorkflowPermissionsAndPinsTest(unittest.TestCase):
    def test_top_level_permissions_are_read_only(self):
        text = CI.read_text()
        block = re.search(r"^permissions:\n((?:  \S.*\n)+)", text, re.M)
        self.assertTrue(block, "no top-level permissions: block")
        self.assertEqual("  contents: read\n", block.group(1))
        self.assertLess(text.index("\npermissions:"), text.index("\njobs:"))
        self.assertNotRegex(text, r":\s*write\b")
        self.assertNotRegex(text, r"permissions:\s*write-all")

    def test_requirements_are_pinned_with_hashes(self):
        reqs = [r for r in re.sub(r"\\\n", " ", REQ.read_text()).splitlines() if r.strip() and not r.startswith("#")]
        names = set()
        for r in reqs:
            with self.subTest(req=r.split()[0]):
                self.assertRegex(r, r"^[A-Za-z0-9_.-]+==[\w.]+(?: ; [^-]+)?\s+--hash=sha256:[0-9a-f]{64}")
                names.add(r.split("==")[0].lower())
        self.assertIn("pytest", names)
        # pytest 8.4's own runtime dependencies (requires_dist without extras) are all listed
        self.assertLessEqual({"iniconfig", "packaging", "pluggy", "pygments", "exceptiongroup", "tomli"}, names)

    def test_every_pip_install_uses_the_hash_pinned_file(self):
        text = CI.read_text() + "\n" + GATE.read_text()
        installs = [l for l in text.splitlines() if "pip install" in l and not l.strip().startswith("#")]
        self.assertGreaterEqual(len(installs), 2, installs)    # the setup step (ci.yml) + the venv fallback (gate script)
        for line in installs:
            with self.subTest(line=line):
                self.assertIn("--require-hashes", line)
                self.assertIn("-r .github/requirements-ci.txt", line)
                self.assertNotIn("--user", line)
        self.assertNotRegex(text, r"pip install --quiet pytest\b")


@unittest.skipUnless(gate_has("bash", "python3", "mktemp"), "needs bash + python3 + mktemp on the gate PATH")
class DesignIntelScratchDirTest(unittest.TestCase):
    """CI #17 run from the real tree: its owned per-run directory lives under $TMPDIR and is removed."""
    def run17(self, tmpdir, home):
        r = subprocess.run(["bash", "-c", section(17)], cwd=ROOT, capture_output=True, text=True,
                           env={"PATH": GATE_PATH, "HOME": str(home), "TMPDIR": str(tmpdir)})
        return r.stdout + r.stderr

    def test_smoke_runs_in_tmpdir_and_removes_its_dir(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            sentinel = pathlib.Path(tmp) / "pre-existing"
            sentinel.write_text("keep\n")
            out = self.run17(tmp, home)
            self.assertIn("fail=0", out)
            self.assertIn("design-intel pack intact + gate runs", out)
            self.assertEqual("keep\n", sentinel.read_text(), "gate changed a file it does not own")
            self.assertEqual([], sorted(p.name for p in pathlib.Path(tmp).glob("shode-di.*")),
                             "owned per-run dir left behind")

    def test_unusable_tmpdir_is_red_not_a_fallback_to_tmp(self):
        with tempfile.TemporaryDirectory() as home:
            out = self.run17(pathlib.Path(home) / "absent", home)
            self.assertIn("mktemp -d failed under", out)
            self.assertIn("fail=1", out)

    def test_no_fixed_tmp_path_is_written(self):
        body = section(17).split('sec "17. ', 1)[1].replace("${TMPDIR:-/tmp}", "")
        self.assertNotRegex(body, r"(?<![\w$}])/tmp/")


class WorkflowTempNamesTest(unittest.TestCase):
    """U22 iter 2 (Chris L2/L3, Sentinel I2): no temp name in the workflow is built from the shell pid (`$$` is
    predictable), and the "Build .plugin artifact" step makes its snapshot with `mktemp` and removes it and the
    unpack dir with an EXIT trap."""
    def build_step(self):
        text = CI.read_text(encoding="utf-8")
        text = text[text.index("\n  pack:\n"):]
        start = text.index("      - name: Build .plugin artifact\n")
        stop = text.index("\n      - name:", start + 1)
        return text[start:stop]

    def test_no_pid_based_temp_name(self):
        self.assertNotIn("$$", CI.read_text(encoding="utf-8"))
        self.assertNotIn("$$", GATE.read_text(encoding="utf-8"))

    def test_build_step_uses_mktemp_and_an_exit_trap(self):
        step = self.build_step()
        self.assertIn('before=$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/pack-tree-before.XXXXXX") || exit 1', step)
        self.assertIn("""d=""; trap 'rm -rf "$before" ${d:+"$d"}' EXIT""", step)
        self.assertLess(step.index("trap 'rm -rf"), step.index("make pack"))


if __name__ == "__main__":
    unittest.main()
