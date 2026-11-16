#!/usr/bin/env python3
"""Cost-free preflight for this one preregistered maintenance campaign."""

import argparse, hashlib, json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true", required=True); parser.parse_args()
    config=json.loads((ROOT/"preregistration-4.2.0.json").read_text()); errors=[]; blockers=[]
    checks={"prompt_sha256":digest(ROOT/"task.md"), "scenario_sha256":digest(ROOT/"scenario.json"), "scorer_sha256":digest(ROOT/"score.py"), "trace_adapter_sha256":digest(ROOT/"trace_adapter.py"), "runner_sha256":digest(ROOT/"runner.py"), "hook_snap_sha256":digest(ROOT.parent/"shape-baseline/hook-snap.py"), "capture_contract_sha256":digest(ROOT/"capture-contract.json"), "schema_contract_sha256":digest(ROOT/"schema-contract.md"), "reviewer_contract_sha256":digest(ROOT/"reviewer-contract.txt"), "capability_evidence_sha256":digest(ROOT/"capability-evidence.json")}
    fixture_bytes=b"".join(p.read_bytes() for p in sorted((ROOT/"fixture").glob("*.py"))); checks["fixture_sha256"]=hashlib.sha256(fixture_bytes).hexdigest()
    errors.extend(key for key, actual in checks.items() if config.get(key) != actual)
    evidence=json.loads((ROOT/"capability-evidence.json").read_text())
    if evidence.get("host_id") != config.get("host_id") or evidence.get("cli_version") != config.get("cli_version") or evidence.get("tool_permissions") != config.get("tool_permissions"): blockers.append("host/CLI/tool-permission evidence is not pinned")
    missing=[name for name in config.get("required_capabilities",[]) if evidence.get("capabilities",{}).get(name) is not True]
    if missing: blockers.append("missing capabilities: "+", ".join(missing))
    candidate=config.get("arms",{}).get("candidate",{}).get("revision","")
    if candidate in ("", "4.2.0-fixed-revision", "UNPINNED"): blockers.append("candidate revision is unpinned")
    limits=config.get("limits",{})
    if not isinstance(limits.get("seconds_per_run"),int) or limits.get("seconds_per_run",0)<=0 or not isinstance(limits.get("max_rework"),int) or limits.get("max_rework",-1)<0: blockers.append("limits are invalid")
    if not isinstance(config.get("cost_ceiling_usd"),(int,float)) or config.get("cost_ceiling_usd",0)<=0: blockers.append("cost ceiling is not positive")
    if config.get("cost_authorized") is not True: blockers.append("cost authority is false")
    with tempfile.TemporaryDirectory(prefix="shode-maintenance-") as tmp:
        isolated=pathlib.Path(tmp)/"fixture"; shutil.copytree(ROOT/"fixture", isolated)
        public=subprocess.run([sys.executable,"-m","pytest","-q","public_test.py"],cwd=isolated,capture_output=True,text=True)
        if public.returncode: errors.append("public_check")
    status="READY" if not errors and not blockers else "BLOCKED"
    print(json.dumps({"status":status,"errors":errors,"blockers":blockers,"model_calls":0},sort_keys=True)); return 0 if not errors else 2


if __name__=="__main__": raise SystemExit(main())
