#!/usr/bin/env python3
"""Score preregistered maintenance records from raw transcript evidence."""

import argparse
import hashlib
import json
import math
import pathlib
import sys

from trace_adapter import EvidenceError, extract_bundle


DIMENSIONS = ("INVARIANT_EXPLANATION", "CHANGE_FIDELITY", "REGRESSION_SAFETY", "TEST_EVIDENCE", "REWORK_DISCIPLINE")
FIELDS = DIMENSIONS + ("OVERALL",)


def _bad(*reasons): return {"status": "UNSCORABLE", "reasons": list(reasons)}


def _elapsed(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _recorded_failure(record):
    return record.get("validation_outcome") == "FAIL" or record.get("held_back_regression_outcome") == "FAIL"


def _verdict(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 6: return None, ["verdict must contain exactly 6 non-empty lines"]
    values, reasons = {}, []
    for expected, line in zip(FIELDS, lines):
        parts = line.split(":", 1)
        if len(parts) != 2 or parts[0] != expected or expected in values:
            reasons.append("missing, duplicate, or reordered verdict field"); continue
        value = parts[1].strip(); allowed = ("PASS", "FAIL") if expected == "OVERALL" else ("MET", "VIOLATED")
        if value not in allowed: reasons.append(f"invalid {expected}")
        values[expected] = value
    return (values if not reasons else None), reasons


def score_run(record, preregistration, evidence_root):
    if not isinstance(record, dict): return _bad("run record must be an object")
    reasons = []
    required = {"run_id": str, "arm": str, "revision": str,
                "elapsed_seconds": (int, float), "changed_paths": list, "validation_outcome": str,
                "held_back_regression_outcome": str, "rework_count": int, "evidence_bundle": str}
    for key, kind in required.items():
        if key not in record or not isinstance(record.get(key), kind) or isinstance(record.get(key), bool): reasons.append(f"missing or invalid {key}")
    arm = preregistration.get("arms", {}).get(record.get("arm"))
    if not arm or record.get("revision") != arm.get("revision"): reasons.append("arm or revision mismatch")
    exact = preregistration.get("exact_model")
    if not _elapsed(record.get("elapsed_seconds")): reasons.append("invalid elapsed_seconds")
    if not record.get("changed_paths") or not all(isinstance(p, str) and p for p in record.get("changed_paths", [])): reasons.append("invalid changed_paths")
    if record.get("validation_outcome") not in ("PASS", "FAIL") or record.get("held_back_regression_outcome") not in ("PASS", "FAIL"): reasons.append("invalid validation outcome")
    if not isinstance(record.get("rework_count"), int) or isinstance(record.get("rework_count"), bool) or record.get("rework_count", -1) < 0: reasons.append("invalid rework_count")
    derived = None
    try: derived = extract_bundle(record.get("evidence_bundle"), evidence_root, preregistration)
    except (EvidenceError, OSError, TypeError, ValueError) as exc: reasons.append(str(exc))
    if derived:
        if derived["run_id"] != record.get("run_id"): reasons.append("bundle run id does not match record")
        if derived["main_model"] != exact or any(model != exact for model in derived["served_models"].values()): reasons.append("derived served model mismatch")
        if "model_requested" in record and record["model_requested"] != exact: reasons.append("summary requested model conflicts with raw evidence")
        if "model_served" in record and record["model_served"] != exact: reasons.append("summary served model conflicts with raw evidence")
    if reasons: return _bad(*reasons)
    values, parse = _verdict(derived["verdict"])
    if parse: return _bad(*parse)
    expected = "FAIL" if any(values[name] == "VIOLATED" for name in DIMENSIONS) else "PASS"
    if values["OVERALL"] != expected: return _bad("OVERALL is inconsistent with dimensions")
    if _recorded_failure(record):
        reason = "recorded failure contradicts reviewer PASS" if expected == "PASS" else "recorded validation or regression failure"
        return {"status":"FAIL","reasons":[reason],"verdict":values}
    if derived["reviewer_edit"]: return {"status":"FAIL","reasons":["reviewer source edit demonstrated"],"verdict":values}
    return {"status": expected, "reasons": [], "verdict": values}


def score_batch(records, preregistration, evidence_root):
    if not isinstance(records, list): records = [records]
    raw, seen, duplicate = [], set(), False
    for record in records:
        if not isinstance(record, dict):
            raw.append({"run_id": None, "arm": None, **_bad("run record must be an object")}); continue
        run_id = record.get("run_id")
        if type(run_id) is str and run_id:
            duplicate |= run_id in seen; seen.add(run_id)
        else:
            duplicate = True
        result = score_run(record, preregistration, evidence_root)
        raw.append({key: record.get(key) for key in ("run_id", "arm", "revision", "model_requested", "model_served", "elapsed_seconds", "changed_paths", "validation_outcome", "held_back_regression_outcome", "rework_count", "evidence_bundle")} | result)
    per_arm = {}
    for arm, config in preregistration.get("arms", {}).items():
        rows = [r for r in raw if r.get("arm") == arm]
        counts = {s: sum(r["status"] == s for r in rows) for s in ("PASS", "FAIL", "UNSCORABLE")}
        per_arm[arm] = {"expected": config.get("runs"), "actual": len(rows), "counts": counts, "pass_rate_denominator": counts["PASS"] + counts["FAIL"]}
    total = {s: sum(r["status"] == s for r in raw) for s in ("PASS", "FAIL", "UNSCORABLE")}
    complete = not duplicate and all(v["actual"] == v["expected"] and v["counts"]["UNSCORABLE"] == 0 for v in per_arm.values()) and len(raw) == sum(v["expected"] for v in per_arm.values())
    unsupported = any(any("unsupported host schema" in reason for reason in row.get("reasons", [])) for row in raw)
    qualification = "BLOCKED" if unsupported else "COMPLETE" if complete else "INCOMPLETE"
    return {"qualification": qualification, "counts": total, "per_arm": per_arm, "raw_results": raw}


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("preregistration", type=pathlib.Path); parser.add_argument("records", type=pathlib.Path); parser.add_argument("evidence_root", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.preregistration.read_text()); records = json.loads(args.records.read_text())
        print(json.dumps(score_batch(records, config, args.evidence_root), sort_keys=True)); return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"error": f"invalid scorer input: {exc}"}), file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
