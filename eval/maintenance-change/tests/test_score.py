import copy, hashlib, importlib.util, json, pathlib, subprocess, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]; REPO=ROOT.parents[1]; sys.path.insert(0,str(ROOT))
SPEC=importlib.util.spec_from_file_location("score",ROOT/"score.py"); SCORE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(SCORE)
TRACE=sys.modules["trace_adapter"]
def oracle(): return json.loads((ROOT/"preregistration-4.2.0.json").read_text())
def verdict(bad=None,overall="PASS"): return "\n".join([f"{x}: {'VIOLATED' if x==bad else 'MET'}" for x in SCORE.DIMENSIONS]+[f"OVERALL: {overall}"])
def dump(path,values,jsonl=True): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(("\n".join(json.dumps(x) for x in values)+"\n") if jsonl else json.dumps(values[0]))

def bundle(root,name="run",review=None,review_edit=False,reviewer_tool=None):
    b=root/name; session="sess-1"; model=oracle()["exact_model"]
    run=[{"type":"system","subtype":"init","session_id":session,"model":model,"claude_code_version":"2.1.286"},{"type":"result","subtype":"success","is_error":False,"session_id":session}]
    main=[]
    for tool,typ,marker,stamp in (("t-impl","build","maintenance-implementer","00:00:01"),("t-rev","verify","maintenance-reviewer","00:00:05")):
        main.append({"type":"assistant","sessionId":session,"timestamp":f"2026-01-01T{stamp}Z","message":{"content":[{"type":"tool_use","name":"Agent","id":tool,"input":{"subagent_type":typ,"model":model,"prompt":marker}}]}})
        done="00:00:04" if tool=="t-impl" else "00:00:09"
        main.append({"type":"user","sessionId":session,"timestamp":f"2026-01-01T{done}Z","message":{"content":[{"type":"tool_result","tool_use_id":tool,"content":"completed"}]}})
    files={"raw/run.jsonl":run,"raw/transcript/main.jsonl":main}
    for aid,tool,typ,start,text in (("impl","t-impl","build","00:00:02","implementation"),("rev","t-rev","verify","00:00:06",review or verdict())):
        content=[{"type":"text","text":text}]
        if aid=="rev" and reviewer_tool: content.insert(0,{"type":"tool_use","id":"rev-call","name":reviewer_tool,"input":{"subagent_type":"verify","prompt":"nested review"} if reviewer_tool in {"Agent","Task"} else {"file_path":"x"} if reviewer_tool!="Bash" else {"command":"printf harmless"}})
        files[f"raw/transcript/subagents/agent-{aid}.jsonl"]=[{"type":"assistant","agentId":aid,"sessionId":session,"isSidechain":True,"timestamp":f"2026-01-01T{start}Z","message":{"model":model,"usage":{"input_tokens":1},"content":content}}]
        files[f"raw/transcript/subagents/agent-{aid}.meta.json"]=[{"toolUseId":tool,"agentType":typ,"spawnDepth":1,"description":typ,"requestShape":"background"}]
    snaps=[{"ts":1.0,"event":"PostToolUse","tool":"Agent","tool_use_id":"t-impl","agent_id":None,"subagent_type":"build","head":"h","files":{}}]
    if reviewer_tool=="Bash": snaps.extend([{"ts":2.0,"event":"PreToolUse","tool":"Bash","tool_use_id":"rev-call","agent_id":"rev","subagent_type":None,"head":"h","files":{}},{"ts":3.0,"event":"PostToolUse","tool":"Bash","tool_use_id":"rev-call","agent_id":"rev","subagent_type":None,"head":"h","files":{"x":"hash"} if review_edit else {}}])
    if reviewer_tool in {"Edit","Write","MultiEdit","NotebookEdit"}: snaps.append({"ts":2.0,"event":"PostToolUse","tool":reviewer_tool,"tool_use_id":"rev-call","agent_id":"rev","subagent_type":None,"head":"h","files":{"x":"hash"}})
    if reviewer_tool in {"Agent","Task"}:
        snaps.extend([{"ts":2.0,"event":"PreToolUse","tool":reviewer_tool,"tool_use_id":"rev-call","agent_id":"rev","subagent_type":"verify","head":"h","files":{}},{"ts":3.0,"event":"PostToolUse","tool":reviewer_tool,"tool_use_id":"rev-call","agent_id":"rev","subagent_type":"verify","head":"h","files":{"x":"hash"} if review_edit else {}}])
    files["raw/snap.jsonl"]=snaps
    for rel,vals in files.items(): dump(b/rel,vals,not rel.endswith(".meta.json"))
    reseal(b); return b

def reseal(b,schema="claude-code-on-disk-v1"):
    rels=["raw/run.jsonl","raw/transcript/main.jsonl","raw/snap.jsonl","raw/transcript/subagents/agent-impl.jsonl","raw/transcript/subagents/agent-impl.meta.json","raw/transcript/subagents/agent-rev.jsonl","raw/transcript/subagents/agent-rev.meta.json"]
    cfg=oracle(); keys=("trace_adapter_sha256","runner_sha256","scorer_sha256","scenario_sha256","reviewer_contract_sha256","hook_snap_sha256","capture_contract_sha256","schema_contract_sha256")
    manifest={"schema":schema,"run_id":b.name,"main":rels[1],"run":rels[0],"snapshot":rels[2],"cli_version":"2.1.286","session_id":"sess-1","protocol_hashes":{k:cfg[k] for k in keys},"files":{r:hashlib.sha256((b/r).read_bytes()).hexdigest() for r in rels},"subagents":[{"jsonl":rels[3],"meta":rels[4]},{"jsonl":rels[5],"meta":rels[6]}]}
    dump(b/"manifest.json",[manifest],False)

def record(b,arm="candidate",run_id=None,**summary):
    d={"run_id":run_id or b.name,"arm":arm,"revision":oracle()["arms"][arm]["revision"],"elapsed_seconds":1.0,"changed_paths":["x"],"validation_outcome":"PASS","held_back_regression_outcome":"PASS","rework_count":0,"evidence_bundle":b.name}; d.update(summary); return d
def score(b,**kw): return SCORE.score_run(record(b,**kw),oracle(),b.parent)
def load_lines(path): return [json.loads(x) for x in path.read_text().splitlines()]

def test_01_valid_pass_and_02_explicit_fail(tmp_path):
    assert score(bundle(tmp_path))["status"]=="PASS"
    assert score(bundle(tmp_path,"fail",verdict("CHANGE_FIDELITY","FAIL")))["status"]=="FAIL"

def test_03_integrity_missing_escape_nonhex_mismatch_and_substitution(tmp_path):
    for name,mut in (("missing","missing"),("nonhex","nonhex"),("mismatch","mismatch")):
        b=bundle(tmp_path,name); m=json.loads((b/"manifest.json").read_text())
        key="raw/transcript/subagents/agent-rev.jsonl"
        if mut=="missing": (b/key).unlink()
        elif mut=="nonhex": m["files"][key]="z"*64; dump(b/"manifest.json",[m],False)
        else: (b/key).write_text("{}\n")
        assert score(b)["status"]=="UNSCORABLE"
    assert SCORE.score_run({**record(bundle(tmp_path,"escape")),"evidence_bundle":"../escape"},oracle(),tmp_path)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"duplicate"); m=json.loads((b/"manifest.json").read_text()); m["subagents"][1]=copy.deepcopy(m["subagents"][0]); dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"

def test_04_malformed_and_nonobject_events(tmp_path):
    for i,payload in enumerate(("{", "[]\n", '"x"\n', "1\n", "null\n")):
        b=bundle(tmp_path,f"bad{i}"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; p.write_text(payload); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    for i,value in enumerate(([], "x", None)):
        b=bundle(tmp_path,f"nested{i}"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]=value; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    for name,target in (("content","content"),("usage","usage")):
        b=bundle(tmp_path,"nested"+name); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"][target]=[] if target=="usage" else None; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"nestedinput"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[0]["message"]["content"][0]["input"]=[]; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"nestedmeta"); p=b/"raw/transcript/subagents/agent-rev.meta.json"; m=json.loads(p.read_text()); m["spawnDepth"]="1"; dump(p,[m],False); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_spawn_depth_requires_exact_integer_one(tmp_path):
    for i,value in enumerate((True,1.0,"1",None,0,2)):
        b=bundle(tmp_path,f"spawn-depth-{i}"); p=b/"raw/transcript/subagents/agent-rev.meta.json"; m=json.loads(p.read_text()); m["spawnDepth"]=value; dump(p,[m],False); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def set_all_session_ids(b,value):
    for rel in ("raw/run.jsonl","raw/transcript/main.jsonl","raw/transcript/subagents/agent-impl.jsonl","raw/transcript/subagents/agent-rev.jsonl"):
        p=b/rel; rows=load_lines(p)
        for row in rows:
            if "session_id" in row: row["session_id"]=value
            if "sessionId" in row: row["sessionId"]=value
        dump(p,rows)
    reseal(b); m=json.loads((b/"manifest.json").read_text()); m["session_id"]=value; dump(b/"manifest.json",[m],False)

def test_all_linked_session_ids_require_nonempty_strings(tmp_path):
    for i,value in enumerate((True,1,1.5,None,"")):
        b=bundle(tmp_path,f"session-scalar-{i}"); set_all_session_ids(b,value); assert score(b)["status"]=="UNSCORABLE"

def test_05_unsupported_schema_and_pinned_semantic_hashes(tmp_path):
    b=bundle(tmp_path,"codex"); reseal(b,"codex-unverified"); assert score(b)["status"]=="UNSCORABLE"
    cfg=oracle(); assert all(len(cfg[k])==64 for k in ("trace_adapter_sha256","runner_sha256","scorer_sha256","reviewer_contract_sha256","capture_contract_sha256","schema_contract_sha256"))
    b=bundle(tmp_path,"semantic"); m=json.loads((b/"manifest.json").read_text()); m["protocol_hashes"]["trace_adapter_sha256"]="0"*64; dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"

def test_06_main_init_missing_and_conflicting(tmp_path):
    for name,mode in (("missing","missing"),("mixed","mixed")):
        b=bundle(tmp_path,name); p=b/"raw/run.jsonl"; rows=load_lines(p); rows=rows[1:] if mode=="missing" else [rows[0],{**rows[0],"model":"wrong"},rows[1]]; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_top_level_run_init_must_precede_terminal_result(tmp_path):
    b=bundle(tmp_path,"result-before-init"); p=b/"raw/run.jsonl"; rows=load_lines(p); dump(p,list(reversed(rows))); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_top_level_parent_field_must_be_absent(tmp_path):
    for target in (0,1):
        for i,value in enumerate((False,True,0,1,"","parent",None)):
            b=bundle(tmp_path,f"parent-{target}-{i}"); p=b/"raw/run.jsonl"; rows=load_lines(p); rows[target]["parent_tool_use_id"]=value; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_top_level_result_must_be_final_run_event(tmp_path):
    b=bundle(tmp_path,"event-after-result"); p=b/"raw/run.jsonl"; rows=load_lines(p); rows.append({"type":"assistant","session_id":"sess-1"}); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_07_requested_and_served_model_negatives(tmp_path):
    for name,target,field,value in (("req","main","model",None),("reqwrong","main","model","wrong"),("served","rev","model",None),("servedwrong","rev","model","wrong")):
        b=bundle(tmp_path,name)
        p=b/("raw/transcript/main.jsonl" if target=="main" else "raw/transcript/subagents/agent-rev.jsonl"); rows=load_lines(p)
        if target=="main": block=rows[2]["message"]["content"][0]["input"]
        else: block=rows[0]["message"]
        if value is None: block.pop(field)
        else: block[field]=value
        dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"mixed"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows.append({**copy.deepcopy(rows[0]),"timestamp":"2026-01-01T00:00:07Z"}); rows[-1]["message"]["model"]="wrong"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_08_summary_models_cannot_repair_or_contradict_raw(tmp_path):
    b=bundle(tmp_path); assert score(b,model_requested="wrong")["status"]=="UNSCORABLE"
    p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["model"]="wrong"; dump(p,rows); reseal(b); assert score(b,model_served=oracle()["exact_model"])["status"]=="UNSCORABLE"

def test_09_and_10_identity_spawn_meta_linkage(tmp_path):
    b=bundle(tmp_path); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["agentId"]="impl"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"meta"); p=b/"raw/transcript/subagents/agent-rev.meta.json"; m=json.loads(p.read_text()); m["toolUseId"]="orphan"; dump(p,[m],False); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"type"); p=b/"raw/transcript/subagents/agent-rev.meta.json"; m=json.loads(p.read_text()); m["agentType"]="build"; dump(p,[m],False); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_11_verdict_only_main_arbitrary_label_zero_multiple(tmp_path):
    b=bundle(tmp_path); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["content"][0]["text"]="role: fresh-reviewer"; dump(p,rows); main=b/"raw/transcript/main.jsonl"; mr=load_lines(main); mr.append({"type":"assistant","sessionId":"sess-1","timestamp":"2026-01-01T00:00:09.5Z","message":{"content":[{"type":"text","text":verdict()}]}}); dump(main,mr); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"multi",verdict()+"\n"+verdict()); assert score(b)["status"]=="UNSCORABLE"

def test_reviewer_verdict_must_full_match_final_text(tmp_path):
    for name,text in (("prefix","prefix\n"+verdict()),("suffix",verdict()+"\nsuffix"),("blank",verdict()+"\n\n"),("extra-line",verdict()+"\nEXTRA")):
        assert score(bundle(tmp_path,"verdict-"+name,review=text))["status"]=="UNSCORABLE"
    assert score(bundle(tmp_path,"verdict-terminal-newline",review=verdict()+"\n"))["status"]=="PASS"
    assert score(bundle(tmp_path,"verdict-crlf",review=verdict().replace("\n","\r\n")+"\r\n"))["status"]=="PASS"

def test_reviewer_text_blocks_require_exact_string_and_single_verdict_block(tmp_path):
    for i,value in enumerate((None,True,1,1.5,[],{})):
        b=bundle(tmp_path,f"verdict-text-scalar-{i}"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["content"].append({"type":"text","text":value}); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    for i,extra in enumerate(("ordinary","",verdict())):
        b=bundle(tmp_path,f"verdict-multiple-text-{i}"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["content"].append({"type":"text","text":extra}); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_multiple_reviewer_verdict_events_are_unscorable(tmp_path):
    b=bundle(tmp_path,"two-verdict-events"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); later=copy.deepcopy(rows[0]); later["timestamp"]="2026-01-01T00:00:07Z"; rows.append(later); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_12_order_wrong_completion_and_cross_session(tmp_path):
    b=bundle(tmp_path); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[2]["timestamp"]="2026-01-01T00:00:03Z"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"cross"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["sessionId"]="other"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"wrongid"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[3]["message"]["content"][0]["tool_use_id"]="other"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_main_spawn_and_completion_require_host_event_roles(tmp_path):
    for name,mutate in (("user-spawn",lambda rows: rows[0].update(type="user")),("assistant-completion",lambda rows: rows[1].update(type="assistant")),("arbitrary-chain",lambda rows: [row.update(type="arbitrary") for row in rows])):
        b=bundle(tmp_path,"envelope-"+name); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); mutate(rows); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_full_windows_top_level_result_completion_and_exact_spawn_count(tmp_path):
    for name,path,stamp in (("ibefore","agent-impl.jsonl","00:00:00"),("iafter","agent-impl.jsonl","00:00:08"),("rbefore","agent-rev.jsonl","00:00:04.5"),("rafter","agent-rev.jsonl","00:00:09.5")):
        b=bundle(tmp_path,name); p=b/f"raw/transcript/subagents/{path}"; rows=load_lines(p); rows[0]["timestamp"]=f"2026-01-01T{stamp}Z"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    for name,mode in (("child","child"),("missing","missing"),("ambiguous","ambiguous")):
        b=bundle(tmp_path,"result"+name); p=b/"raw/run.jsonl"; rows=load_lines(p)
        if mode=="child": rows[1]["parent_tool_use_id"]="parent"
        elif mode=="missing": rows=rows[:1]
        else: rows.append(copy.deepcopy(rows[1]))
        dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    for i,value in enumerate((True,)):
        b=bundle(tmp_path,f"complete{i}"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); block=rows[1]["message"]["content"][0]
        block["is_error"]=value
        dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"extra"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows.insert(1,copy.deepcopy(rows[0])); rows[1]["message"]["content"][0]["id"]="t-extra"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_completion_error_field_exact_optional_false(tmp_path):
    for i,value in enumerate((True,"true",1,0,None)):
        b=bundle(tmp_path,f"completion-error-{i}"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[1]["message"]["content"][0]["is_error"]=value; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"completion-explicit-false"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[1]["message"]["content"][0]["is_error"]=False; dump(p,rows); reseal(b); assert score(b)["status"]=="PASS"
    assert score(bundle(tmp_path,"completion-absent"))["status"]=="PASS"

def test_reviewer_final_text_requires_monotonic_unique_chronology(tmp_path):
    b=bundle(tmp_path,"ordinary-last"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); later=copy.deepcopy(rows[0]); later["timestamp"]="2026-01-01T00:00:07Z"; later["message"]["content"]=[{"type":"text","text":"ordinary follow-up"}]; rows.append(later); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"reverse"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); earlier=copy.deepcopy(rows[0]); earlier["timestamp"]="2026-01-01T00:00:05.5Z"; rows.append(earlier); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"equal"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows.append(copy.deepcopy(rows[0])); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_all_subagent_row_timestamps_are_strictly_unique(tmp_path):
    b=bundle(tmp_path,"duplicate-empty-assistant"); p=b/"raw/transcript/subagents/agent-impl.jsonl"; rows=load_lines(p); extra=copy.deepcopy(rows[0]); extra["message"]["content"]=[]; rows.append(extra); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"duplicate-user-tool-row"); p=b/"raw/transcript/subagents/agent-impl.jsonl"; rows=load_lines(p); extra=copy.deepcopy(rows[0]); extra["type"]="user"; extra["message"]={"content":[]}; rows.append(extra); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_13_reviewer_edit_fail_missing_attribution_unscorable(tmp_path):
    assert score(bundle(tmp_path,"edit",review_edit=True,reviewer_tool="Bash"))["status"]=="FAIL"
    for tool in ("Edit","Write"): assert score(bundle(tmp_path,"tool"+tool,reviewer_tool=tool))["status"]=="FAIL"
    assert score(bundle(tmp_path,"harmless-bash",reviewer_tool="Bash"))["status"]=="PASS"
    b=bundle(tmp_path,"ambiguous-bash",reviewer_tool="Bash"); p=b/"raw/snap.jsonl"; dump(p,[load_lines(p)[0]]); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"noattr"); p=b/"raw/snap.jsonl"; p.unlink(); assert score(b)["status"]=="UNSCORABLE"

def test_14_unknown_host_blocked_and_15_malformed_batch_cli(tmp_path):
    b=bundle(tmp_path,"unknown"); reseal(b,"unknown"); assert score(b)["status"]=="UNSCORABLE"
    assert SCORE.score_batch([None,"x",[]],oracle(),tmp_path)["counts"]["UNSCORABLE"]==3
    bad=tmp_path/"bad.json"; bad.write_text("{"); r=subprocess.run([sys.executable,str(ROOT/"score.py"),str(ROOT/"preregistration-4.2.0.json"),str(bad),str(tmp_path)],capture_output=True,text=True); assert r.returncode==2

def test_16_batch_5_plus_5_unique_and_incomplete(tmp_path):
    rows=[]
    for arm in ("candidate","baseline"):
        for i in range(5): rows.append(record(bundle(tmp_path,f"{arm}-{i}"),arm))
    out=SCORE.score_batch(rows,oracle(),tmp_path); assert out["qualification"]=="COMPLETE" and out["per_arm"]["candidate"]["actual"]==5
    assert SCORE.score_batch(rows[:-1],oracle(),tmp_path)["qualification"]=="INCOMPLETE"
    dup=rows+[copy.deepcopy(rows[0])]; assert SCORE.score_batch(dup,oracle(),tmp_path)["qualification"]=="INCOMPLETE"

def test_batch_malformed_run_ids_are_disclosed_unscorable(tmp_path):
    b=bundle(tmp_path,"bad-run-id")
    for value in ([],{},None,True,1,1.5,""):
        row=record(b); row["run_id"]=value; out=SCORE.score_batch([row],oracle(),tmp_path); assert out["qualification"]=="INCOMPLETE" and out["counts"]["UNSCORABLE"]==1 and out["raw_results"][0]["run_id"]==value

def test_recorded_validation_or_regression_failure_scores_fail(tmp_path):
    for validation,held in (("FAIL","PASS"),("PASS","FAIL"),("FAIL","FAIL")):
        out=score(bundle(tmp_path,f"outcome-{validation}-{held}"),validation_outcome=validation,held_back_regression_outcome=held); assert out["status"]=="FAIL" and any("recorded failure contradicts reviewer PASS" in reason for reason in out["reasons"])
    out=score(bundle(tmp_path,"outcome-consistent",verdict("REGRESSION_SAFETY","FAIL")),held_back_regression_outcome="FAIL"); assert out["status"]=="FAIL" and any("recorded validation or regression failure" in reason for reason in out["reasons"])

def test_elapsed_seconds_must_be_finite_nonnegative_number(tmp_path):
    b=bundle(tmp_path,"elapsed");
    for value in (float("nan"),float("inf"),float("-inf"),True,-1.0): assert SCORE.score_run(record(b,elapsed_seconds=value),oracle(),tmp_path)["status"]=="UNSCORABLE"
    for value in (0,0.0,1,1.5): assert SCORE.score_run(record(b,elapsed_seconds=value),oracle(),tmp_path)["status"]=="PASS"

def test_trust_boundary_representative_type_matrix(tmp_path):
    for i,value in enumerate((True,1,None,"")):
        b=bundle(tmp_path,f"manifest-run-id-{i}"); m=json.loads((b/"manifest.json").read_text()); m["run_id"]=value; dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"
    for i,value in enumerate((float("nan"),float("inf"),True,0,"later")):
        b=bundle(tmp_path,f"snapshot-ts-{i}"); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows[0]["ts"]=value; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"manifest-files-container"); m=json.loads((b/"manifest.json").read_text()); m["files"]=[]; dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"subagent-wrong-tool-role",reviewer_tool="Edit"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["type"]="user"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_17_readme_cli_and_preflight_not_run(tmp_path):
    readme=(ROOT/"README.md").read_text(); assert "<preregistration> <records.json> <evidence-root>" in readme
    runner=(ROOT/"runner.py").read_text(); assert "--capability" not in runner
    r=subprocess.run([sys.executable,str(ROOT/"runner.py"),"--preflight"],capture_output=True,text=True); report=json.loads(r.stdout.splitlines()[-1]); assert report["status"]=="BLOCKED" and report["model_calls"]==0

def test_snapshot_schema_attribution_is_fail_closed(tmp_path):
    mutations=(
        ("string-ts",lambda rows: rows[-1].update(ts="later")),
        ("wrong-event",lambda rows: rows[-1].update(event="PreToolUse")),
        ("wrong-tool",lambda rows: rows[-1].update(tool="Read")),
        ("wrong-actor",lambda rows: rows[-1].update(agent_id="impl")),
        ("wrong-type",lambda rows: rows[-1].update(subagent_type="verify")),
        ("bad-files",lambda rows: rows[-1].update(files=[])),
    )
    for name,mutate in mutations:
        b=bundle(tmp_path,name,reviewer_tool="Bash"); p=b/"raw/snap.jsonl"; rows=load_lines(p); mutate(rows); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"missing-baseline",reviewer_tool="Bash"); p=b/"raw/snap.jsonl"; rows=load_lines(p); dump(p,[rows[-1]]); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"duplicate-attribution",review_edit=True,reviewer_tool="Bash"); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows.append({**copy.deepcopy(rows[-1]),"ts":3.0,"files":{}}); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"duplicate-time",reviewer_tool="Bash"); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows[-1]["ts"]=rows[0]["ts"]; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_reviewer_mutating_and_unknown_tool_policy(tmp_path):
    for tool in ("Edit","Write","MultiEdit","NotebookEdit"): assert score(bundle(tmp_path,"direct-"+tool,reviewer_tool=tool))["status"]=="FAIL"
    assert score(bundle(tmp_path,"readonly",reviewer_tool="Read"))["status"]=="PASS"
    assert score(bundle(tmp_path,"unknown-tool",reviewer_tool="MysteryTool"))["status"]=="UNSCORABLE"

def test_manifest_inventory_semantic_hashes_and_tool_identity(tmp_path):
    b=bundle(tmp_path,"manifest-path"); m=json.loads((b/"manifest.json").read_text()); key="raw/run.jsonl"; m["files"]["../run.jsonl"]=m["files"].pop(key); m["run"]="../run.jsonl"; dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"extra-file"); (b/"extra.jsonl").write_text("{}\n"); m=json.loads((b/"manifest.json").read_text()); m["files"]["extra.jsonl"]=hashlib.sha256((b/"extra.jsonl").read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"
    for key in ("trace_adapter_sha256","runner_sha256","scorer_sha256","reviewer_contract_sha256","scenario_sha256","hook_snap_sha256","capture_contract_sha256","schema_contract_sha256"):
        b=bundle(tmp_path,"hash-"+key); m=json.loads((b/"manifest.json").read_text()); m["protocol_hashes"][key]="0"*64; dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"same-tool-id"); p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[2]["message"]["content"][0]["id"]="t-impl"; rows[3]["message"]["content"][0]["tool_use_id"]="t-impl"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def test_implementer_served_model_and_batch_unknown_host(tmp_path):
    for name,value in (("missing",None),("wrong","wrong")):
        b=bundle(tmp_path,"impl-served-"+name); p=b/"raw/transcript/subagents/agent-impl.jsonl"; rows=load_lines(p)
        if value is None: rows[0]["message"].pop("model")
        else: rows[0]["message"]["model"]=value
        dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"batch-unknown"); reseal(b,"unknown"); out=SCORE.score_batch([record(b)],oracle(),tmp_path); assert out["qualification"]=="BLOCKED" and out["counts"]["UNSCORABLE"]==1
    assert SCORE.score_batch([record(bundle(tmp_path,"ordinary-unscorable"),model_requested="wrong")],oracle(),tmp_path)["qualification"]=="INCOMPLETE"

def test_real_capture_shape_and_three_argument_cli(tmp_path):
    sample=REPO/"eval/shape-baseline/results/3.17.2-dryrun/S4/r1/raw/run.jsonl"; rows=load_lines(sample); init=next(x for x in rows if x.get("subtype")=="init"); result=next(x for x in rows if x.get("type")=="result")
    meta_path=next((sample.parent/"transcript/subagents").glob("*.meta.json")); meta=json.loads(meta_path.read_text()); snaps=load_lines(sample.parent/"snap.jsonl")
    assert init["claude_code_version"]=="2.1.286" and "timestamp" not in result
    assert {"toolUseId","agentType","spawnDepth"} <= set(meta) and "agentId" not in meta and "sessionId" not in meta
    assert any(x["event"]=="PreToolUse" and x["tool"]=="Agent" for x in snaps) and all(isinstance(x["ts"],(int,float)) for x in snaps)
    b=bundle(tmp_path,"cli-smoke"); records=tmp_path/"records.json"; records.write_text(json.dumps([record(b)])); r=subprocess.run([sys.executable,str(ROOT/"score.py"),str(ROOT/"preregistration-4.2.0.json"),str(records),str(tmp_path)],capture_output=True,text=True); assert r.returncode==0 and json.loads(r.stdout)["counts"]["PASS"]==1
    malformed=tmp_path/"manifest.json"; malformed.write_text("{"); r=subprocess.run([sys.executable,str(ROOT/"score.py"),str(malformed),str(records),str(tmp_path)],capture_output=True,text=True); assert r.returncode==2 and "error" in r.stderr.lower()
    (b/"manifest.json").write_text("{"); r=subprocess.run([sys.executable,str(ROOT/"score.py"),str(ROOT/"preregistration-4.2.0.json"),str(records),str(tmp_path)],capture_output=True,text=True); assert r.returncode==0 and json.loads(r.stdout)["counts"]["UNSCORABLE"]==1

def add_snapshot(b,**values):
    p=b/"raw/snap.jsonl"; rows=load_lines(p); rows.append({"ts":rows[-1]["ts"]+1,"event":"PostToolUse","tool":"Edit","tool_use_id":"orphan","agent_id":"rev","subagent_type":None,"head":"changed","files":{"x":"changed"},**values}); dump(p,rows); reseal(b)

def test_bidirectional_reviewer_snapshot_reconciliation(tmp_path):
    for tool in ("Edit","Write","Bash"):
        b=bundle(tmp_path,"orphan-changed-"+tool); add_snapshot(b,tool=tool); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"orphan-benign"); add_snapshot(b,tool="Bash",head="h",files={}); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"mismatch"); add_snapshot(b,tool="Write",tool_use_id="rev-call"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["content"].insert(0,{"type":"tool_use","id":"rev-call","name":"Edit","input":{"file_path":"x"}}); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"implementer-edit"); add_snapshot(b,tool="NotebookEdit",tool_use_id="impl-call",agent_id="impl"); assert score(b)["status"]=="PASS"

def test_bash_same_call_pair_cannot_be_masked_by_foreign_snapshot(tmp_path):
    b=bundle(tmp_path,"masked-bash",reviewer_tool="Bash",review_edit=True); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows.insert(-1,{"ts":2.5,"event":"PostToolUse","tool":"Edit","tool_use_id":"impl-late","agent_id":"impl","subagent_type":None,"head":"h","files":{"x":"hash"}}); dump(p,rows); reseal(b); assert score(b)["status"]=="FAIL"

def add_conflicting_reviewer_call_pair(b,actor,tool="Bash"):
    p=b/"raw/snap.jsonl"; rows=load_lines(p); rows[-1:-1]=[{"ts":2.25,"event":"PreToolUse","tool":tool,"tool_use_id":"rev-call","agent_id":actor,"subagent_type":None,"head":"h","files":{}},{"ts":2.5,"event":"PostToolUse","tool":tool,"tool_use_id":"rev-call","agent_id":actor,"subagent_type":None,"head":"changed","files":{"x":"hash"}}]; dump(p,rows); reseal(b)

def test_reviewer_call_id_rejects_foreign_or_missing_actor(tmp_path):
    for name,actor in (("foreign","impl"),("none",None)):
        b=bundle(tmp_path,"call-actor-"+name,reviewer_tool="Bash"); add_conflicting_reviewer_call_pair(b,actor); assert score(b)["status"]=="UNSCORABLE"

def test_exact_subagent_filename_schema(tmp_path):
    for arbitrary in ("reviewer.jsonl","agent-.jsonl","agent-bad.id.jsonl"):
        b=bundle(tmp_path,"filename-"+arbitrary.replace(".","-")); old=b/"raw/transcript/subagents/agent-rev.jsonl"; new=b/("raw/transcript/subagents/"+arbitrary); rows=load_lines(old); derived=pathlib.Path(arbitrary).stem.removeprefix("agent-"); rows[0]["agentId"]=derived; dump(new,rows); old.unlink(); m=json.loads((b/"manifest.json").read_text()); oldrel=m["subagents"][1]["jsonl"]; newrel="raw/transcript/subagents/"+arbitrary; m["subagents"][1]["jsonl"]=newrel; m["files"].pop(oldrel); m["files"][newrel]=hashlib.sha256(new.read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False); assert score(b)["status"]=="UNSCORABLE"

def rename_reviewer_meta(b,basename):
    old=b/"raw/transcript/subagents/agent-rev.meta.json"; new=b/("raw/transcript/subagents/"+basename); new.write_bytes(old.read_bytes()); old.unlink(); m=json.loads((b/"manifest.json").read_text()); oldrel=m["subagents"][1]["meta"]; newrel="raw/transcript/subagents/"+basename; m["subagents"][1]["meta"]=newrel; m["files"].pop(oldrel); m["files"][newrel]=hashlib.sha256(new.read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False)

def test_exact_paired_meta_filename_schema(tmp_path):
    for basename in ("reviewer.meta.json","agent-other.meta.json","agent-.meta.json","agent-bad.id.meta.json","agent-bad!.meta.json"):
        b=bundle(tmp_path,"meta-name-"+hashlib.sha256(basename.encode()).hexdigest()[:8]); rename_reviewer_meta(b,basename); assert score(b)["status"]=="UNSCORABLE"

def test_agent_task_snapshot_event_cardinality(tmp_path):
    for tool in ("Agent","Task"):
        assert score(bundle(tmp_path,"nested-"+tool,reviewer_tool=tool))["status"]=="PASS"
        assert score(bundle(tmp_path,"nested-changed-"+tool,reviewer_tool=tool,review_edit=True))["status"]=="FAIL"
        for event in ("PreToolUse","PostToolUse"):
            b=bundle(tmp_path,f"{tool}-missing-{event}",reviewer_tool=tool); p=b/"raw/snap.jsonl"; rows=[x for x in load_lines(p) if not (x.get("tool_use_id")=="rev-call" and x.get("event")==event)]; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
        b=bundle(tmp_path,tool+"-wrong-type",reviewer_tool=tool); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows[-1]["subagent_type"]="build"; dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"
    b=bundle(tmp_path,"post-only-extra-pre",reviewer_tool="Edit"); p=b/"raw/snap.jsonl"; rows=load_lines(p); extra=copy.deepcopy(rows[-1]); extra["ts"]=1.5; extra["event"]="PreToolUse"; rows.insert(-1,extra); dump(p,rows); reseal(b); assert score(b)["status"]=="UNSCORABLE"

def mutant_adapter(tmp_path,old,new):
    source=(ROOT/"trace_adapter.py").read_text(); assert source.count(old)==1
    target=tmp_path/("mutant-"+hashlib.sha256(old.encode()).hexdigest()[:8]+".py"); target.write_text(source.replace(old,new)); spec=importlib.util.spec_from_file_location(target.stem,target); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module,target

def assert_guard_mutant_killed(tmp_path,name,mutate,old,new):
    b=bundle(tmp_path,name); mutate(b)
    try: TRACE.extract_bundle(b.name,tmp_path,oracle())
    except TRACE.EvidenceError: pass
    else: raise AssertionError("original guard did not reject probe")
    module,target=mutant_adapter(tmp_path,old,new); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["host"]=="claude"

def test_critical_guard_mutants_are_killed(tmp_path):
    def served(b):
        p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["model"]="wrong"; dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-model",served,'if models != {preregistration.get("exact_model")}: raise EvidenceError("served model missing, wrong, or mixed")','if False: raise EvidenceError("served model missing, wrong, or mixed")')
    def meta(b):
        p=b/"raw/transcript/subagents/agent-rev.meta.json"; row=json.loads(p.read_text()); row["agentType"]="build"; dump(p,[row],False); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-meta",meta,'meta.get("agentType") != inp.get("subagent_type")','False')
    def same_actor(b):
        p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["agentId"]="impl"; dump(p,rows)
        newrel="raw/transcript/subagents/other/agent-impl.jsonl"; (b/newrel).parent.mkdir(parents=True); p.rename(b/newrel); m=json.loads((b/"manifest.json").read_text()); oldrel=m["subagents"][1]["jsonl"]; m["subagents"][1]["jsonl"]=newrel; m["files"].pop(oldrel); m["files"][newrel]=hashlib.sha256((b/newrel).read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False)
        old=b/"raw/transcript/subagents/agent-rev.meta.json"; meta_rel="raw/transcript/subagents/other/agent-impl.meta.json"; old.rename(b/meta_rel); m=json.loads((b/"manifest.json").read_text()); oldrel=m["subagents"][1]["meta"]; m["subagents"][1]["meta"]=meta_rel; m["files"].pop(oldrel); m["files"][meta_rel]=hashlib.sha256((b/meta_rel).read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False)
    assert_guard_mutant_killed(tmp_path,"mut-identity",same_actor,'if imp["agent_id"] == rev["agent_id"] or imp["tool_id"] == rev["tool_id"]: raise EvidenceError("actors are not distinct")','if False: raise EvidenceError("actors are not distinct")')
    def order(b):
        p=b/"raw/transcript/subagents/agent-impl.jsonl"; rows=load_lines(p); rows[0]["timestamp"]="2026-01-01T00:00:04.500000Z"; dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-order",order,'if not (imp["spawn"] <= imp["start"] <= imp["end"] <= imp["complete"] < rev["spawn"] <= rev["start"] <= rev["end"] <= rev["complete"]):','if False:')
    def bundle_hash(b): (b/"raw/run.jsonl").write_text((b/"raw/run.jsonl").read_text()+" ")
    assert_guard_mutant_killed(tmp_path,"mut-hash",bundle_hash,'if hashlib.sha256(path.read_bytes()).hexdigest() != expected: raise EvidenceError("bundle hash mismatch")','if False: raise EvidenceError("bundle hash mismatch")')
    def host(b):
        m=json.loads((b/"manifest.json").read_text()); m["schema"]="codex-unverified"; dump(b/"manifest.json",[m],False)
    assert_guard_mutant_killed(tmp_path,"mut-host",host,'if manifest.get("schema") != "claude-code-on-disk-v1": raise EvidenceError("unsupported host schema")','if False: raise EvidenceError("unsupported host schema")')

def test_filename_schema_guard_mutant_is_killed(tmp_path):
    def arbitrary_filename(b):
        old=b/"raw/transcript/subagents/agent-rev.jsonl"; new=b/"raw/transcript/subagents/reviewer.jsonl"; rows=load_lines(old); rows[0]["agentId"]="reviewer"; dump(new,rows); old.unlink(); m=json.loads((b/"manifest.json").read_text()); oldrel=m["subagents"][1]["jsonl"]; newrel="raw/transcript/subagents/reviewer.jsonl"; m["subagents"][1]["jsonl"]=newrel; m["files"].pop(oldrel); m["files"][newrel]=hashlib.sha256(new.read_bytes()).hexdigest(); dump(b/"manifest.json",[m],False)
        rename_reviewer_meta(b,"agent-reviewer.meta.json")
    assert_guard_mutant_killed(tmp_path,"mut-filename",arbitrary_filename,'match = AGENT_FILE.fullmatch(pathlib.Path(pair["jsonl"]).name)\n        if not match: raise EvidenceError("subagent transcript filename invalid")\n        agent_id = match.group(1)','agent_id = pathlib.Path(pair["jsonl"]).stem.removeprefix("agent-")')

def test_paired_meta_filename_guard_mutant_is_killed(tmp_path):
    def arbitrary_meta(b): rename_reviewer_meta(b,"reviewer.meta.json")
    assert_guard_mutant_killed(tmp_path,"mut-meta-filename",arbitrary_meta,'meta_match = META_FILE.fullmatch(pathlib.Path(pair["meta"]).name)\n        if not meta_match or meta_match.group(1) != agent_id: raise EvidenceError("paired meta filename invalid")','meta_match = None')

def test_run_order_guard_mutant_is_killed(tmp_path):
    def reverse_run(b):
        p=b/"raw/run.jsonl"; dump(p,list(reversed(load_lines(p)))); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-run-order",reverse_run,'if run.index(init[0]) >= run.index(results[0]): raise EvidenceError("terminal result precedes run init")\n    if run.index(results[0]) != len(run) - 1: raise EvidenceError("terminal result is not final run event")','if False: raise EvidenceError("terminal result precedes run init")\n    if False: raise EvidenceError("terminal result is not final run event")')

def test_terminal_position_guard_mutant_is_killed(tmp_path):
    def append_after_result(b):
        p=b/"raw/run.jsonl"; rows=load_lines(p); rows.append({"type":"assistant","session_id":"sess-1"}); dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-terminal-position",append_after_result,'if run.index(results[0]) != len(run) - 1: raise EvidenceError("terminal result is not final run event")','if False: raise EvidenceError("terminal result is not final run event")')

def test_bash_same_call_pair_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-bash-pair",reviewer_tool="Bash",review_edit=True); p=b/"raw/snap.jsonl"; rows=load_lines(p); rows.insert(-1,{"ts":2.5,"event":"PostToolUse","tool":"Edit","tool_use_id":"impl-late","agent_id":"impl","subagent_type":None,"head":"h","files":{"x":"hash"}}); dump(p,rows); reseal(b)
    assert TRACE.extract_bundle(b.name,tmp_path,oracle())["reviewer_edit"] is True
    module,target=mutant_adapter(tmp_path,'prior = by_event["PreToolUse"][1]','prior = snapshots[index - 1]'); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["reviewer_edit"] is False

def test_exact_verdict_fullmatch_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-verdict-fullmatch",review="prefix\n"+verdict()+"\nsuffix")
    try: TRACE.extract_bundle(b.name,tmp_path,oracle())
    except TRACE.EvidenceError: pass
    else: raise AssertionError("original exact verdict guard accepted extra text")
    module,target=mutant_adapter(tmp_path,"if VERDICT_CONTRACT.fullmatch(normalized)","if VERDICT_CONTRACT.search(normalized)"); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["host"]=="claude"

def test_reviewer_call_actor_binding_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-call-actor-probe",reviewer_tool="Bash"); add_conflicting_reviewer_call_pair(b,"impl")
    try: TRACE.extract_bundle(b.name,tmp_path,oracle())
    except TRACE.EvidenceError: pass
    else: raise AssertionError("original actor binding guard accepted foreign actor")
    module,target=mutant_adapter(tmp_path,'if any(sn["agent_id"] != rev["agent_id"] or sn["tool"] != name for _, sn in call_snapshots): raise EvidenceError("reviewer call snapshot actor or tool mismatch")\n        matches = call_snapshots','if False: raise EvidenceError("reviewer call snapshot actor or tool mismatch")\n        matches = [(index, sn) for index, sn in reviewer_snapshots if sn["tool_use_id"] == call_id and sn["tool"] == name]'); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["host"]=="claude"

def test_verdict_event_cardinality_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-verdict-events"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); later=copy.deepcopy(rows[0]); later["timestamp"]="2026-01-01T00:00:07Z"; rows.append(later); dump(p,rows); reseal(b)
    try: TRACE.extract_bundle(b.name,tmp_path,oracle())
    except TRACE.EvidenceError: pass
    else: raise AssertionError("original verdict event guard accepted multiple verdicts")
    module,target=mutant_adapter(tmp_path,'if len(rev["verdict_events"]) != 1: raise EvidenceError("reviewer verdict event count is not exactly one")','if False: raise EvidenceError("reviewer verdict event count is not exactly one")'); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["verdict"]==verdict()

def test_main_event_role_binding_mutant_is_killed(tmp_path):
    def user_spawn(b):
        p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[0]["type"]="user"; dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-main-role",user_spawn,'if event.get("type") != "assistant": raise EvidenceError("spawn block has wrong event role")','if False: raise EvidenceError("spawn block has wrong event role")')

def test_spawn_depth_exact_type_mutant_is_killed(tmp_path):
    def boolean_depth(b):
        p=b/"raw/transcript/subagents/agent-rev.meta.json"; row=json.loads(p.read_text()); row["spawnDepth"]=True; dump(p,[row],False); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-spawn-depth",boolean_depth,'if type(meta.get("spawnDepth")) is not int or meta["spawnDepth"] != 1: raise EvidenceError("spawn depth invalid")','if not isinstance(meta.get("spawnDepth"), int) or meta["spawnDepth"] != 1: raise EvidenceError("spawn depth invalid")')

def test_session_exact_type_mutant_is_killed(tmp_path):
    assert_guard_mutant_killed(tmp_path,"mut-session-type",lambda b: set_all_session_ids(b,True),'return type(value) is str and bool(value)','return bool(value)')

def test_completion_error_exact_type_mutant_is_killed(tmp_path):
    def string_error(b):
        p=b/"raw/transcript/main.jsonl"; rows=load_lines(p); rows[1]["message"]["content"][0]["is_error"]="true"; dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-completion-error",string_error,'if "is_error" in block and (type(block["is_error"]) is not bool or block["is_error"] is not False): raise EvidenceError("completion error field invalid")','if block.get("is_error") is True: raise EvidenceError("completion error field invalid")')

def test_top_level_parent_shape_mutant_is_killed(tmp_path):
    def false_parent(b):
        p=b/"raw/run.jsonl"; rows=load_lines(p); rows[1]["parent_tool_use_id"]=False; dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-parent-shape",false_parent,'return "parent_tool_use_id" not in event','return not event.get("parent_tool_use_id")')

def test_subagent_timestamp_uniqueness_mutant_is_killed(tmp_path):
    def duplicate_empty(b):
        p=b/"raw/transcript/subagents/agent-impl.jsonl"; rows=load_lines(p); extra=copy.deepcopy(rows[0]); extra["message"]["content"]=[]; rows.append(extra); dump(p,rows); reseal(b)
    assert_guard_mutant_killed(tmp_path,"mut-subagent-time",duplicate_empty,'if times != sorted(times) or len(set(times)) != len(times): raise EvidenceError("subagent timestamps are non-monotonic or ambiguous")','if times != sorted(times): raise EvidenceError("subagent timestamps are non-monotonic or ambiguous")')

def mutant_score(tmp_path,old,new):
    source=(ROOT/"score.py").read_text(); assert source.count(old)==1; target=tmp_path/("score-mutant-"+hashlib.sha256(old.encode()).hexdigest()[:8]+".py"); target.write_text(source.replace(old,new)); spec=importlib.util.spec_from_file_location(target.stem,target); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module,target

def score_with_mutant(b,tmp_path,old,new,**summary):
    module,target=mutant_score(tmp_path,old,new); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["scorer_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["scorer_sha256"]=digest; dump(b/"manifest.json",[manifest],False); return module.score_run(record(b,**summary),cfg,tmp_path)

def test_recorded_failure_policy_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-outcome"); original=score(b,validation_outcome="FAIL"); assert original["status"]=="FAIL"
    assert score_with_mutant(b,tmp_path,'return record.get("validation_outcome") == "FAIL" or record.get("held_back_regression_outcome") == "FAIL"','return False',validation_outcome="FAIL")["status"]=="PASS"

def test_elapsed_finite_guard_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-elapsed"); assert SCORE.score_run(record(b,elapsed_seconds=float("inf")),oracle(),tmp_path)["status"]=="UNSCORABLE"
    assert score_with_mutant(b,tmp_path,'return type(value) in (int, float) and math.isfinite(value) and value >= 0','return type(value) in (int, float) and value >= 0',elapsed_seconds=float("inf"))["status"]=="PASS"

def test_text_block_exact_type_mutant_is_killed(tmp_path):
    b=bundle(tmp_path,"mut-text-type"); p=b/"raw/transcript/subagents/agent-rev.jsonl"; rows=load_lines(p); rows[0]["message"]["content"].append({"type":"text","text":1}); dump(p,rows); reseal(b)
    try: TRACE.extract_bundle(b.name,tmp_path,oracle())
    except TRACE.EvidenceError: pass
    else: raise AssertionError("original text guard accepted malformed text")
    module,target=mutant_adapter(tmp_path,'if any(block.get("type") == "text" and type(block.get("text")) is not str for block in content): raise EvidenceError("text block value must be a string")','if False: raise EvidenceError("text block value must be a string")'); cfg=oracle(); digest=hashlib.sha256(target.read_bytes()).hexdigest(); cfg["trace_adapter_sha256"]=digest; manifest=json.loads((b/"manifest.json").read_text()); manifest["protocol_hashes"]["trace_adapter_sha256"]=digest; dump(b/"manifest.json",[manifest],False)
    assert module.extract_bundle(b.name,tmp_path,cfg)["host"]=="claude"
