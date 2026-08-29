"""Reviewer A runner. Run from experiments/foundry-pass-2:

    python3 tools/run_reviewer_a.py identity      bind identity record + probes
    python3 tools/run_reviewer_a.py review [N]    review next N unreviewed shards
    python3 tools/run_reviewer_a.py status

Identity is bound (and leak probes pass) BEFORE the first real review; the
identity digest is part of every task prompt, so a review can never run
against an unbound identity. Outputs: out/reviewer-a/.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)

from engine import canon, reviewer  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(PASS2, "..", ".."))
ARI = os.path.join(PASS2, "evaluator", "ari")
OUT = os.path.join(PASS2, "out")
A_OUT = os.path.join(OUT, "reviewer-a")
MODEL = os.environ.get("FOUNDRY_REVIEWER_A_MODEL", "claude-sonnet-5")
FORBIDDEN_TARGET = os.path.join(REPO_ROOT, "README.md")


def _sha(path):
    return canon.file_sha256(path)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def bundle_digests():
    bundle_path = os.path.join(OUT, "review-input-bundle.json")
    bundle = canon.load_json(bundle_path)
    return {
        "CONTRACT_SHA256": bundle["bindings"]["reviewer_contract"]["sha256"],
        "REVIEW_INPUT_BUNDLE_SHA256": _sha(bundle_path),
        "SHARD_MANIFEST_SHA256": bundle["shard_manifest"]["sha256"],
    }


def schema_validator(output):
    """Ari's validator, run as delivered (node + ajv from the repo)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(output, f)
        path = f.name
    try:
        proc = subprocess.run(
            ["node", os.path.join(ARI, "validate-reviewer-output-v0.1.mjs"),
             os.path.join(ARI, "reviewer-output-v0.1.schema.json"), path],
            capture_output=True, text=True,
            env={**os.environ, "DWTC_REPO_ROOT": REPO_ROOT})
    finally:
        os.unlink(path)
    return proc.returncode == 0, {
        "validator_sha256": _sha(os.path.join(
            ARI, "validate-reviewer-output-v0.1.mjs")),
        "returncode": proc.returncode,
        "stderr_head": proc.stderr[:2000],
    }


def make_session(system_prompt, cwd):
    return reviewer.IsolatedSession(MODEL, system_prompt, cwd)


def cli_version():
    proc = subprocess.run(["claude", "--version"], capture_output=True,
                          text=True)
    return proc.stdout.strip() or proc.stderr.strip()


def bind_identity():
    os.makedirs(A_OUT, exist_ok=True)
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = _read(os.path.join(ARI, "reviewer-task-template-v0.1.md"))
    digests = bundle_digests()
    cwd = tempfile.mkdtemp(prefix="foundry-reviewer-a-")
    session = make_session(system_prompt, cwd)
    # Probes run with a provisional identity digest (all zeros): the probe
    # prompts are not reviews, and the bound identity includes the probe
    # transcript digest, so it cannot exist before the probes do.
    probe_digests = dict(digests, REVIEWER_IDENTITY_SHA256="0" * 64)
    # Evidence-first: the harness writes every raw prompt and response to
    # this path as it happens, and the complete failed-preflight record
    # before any exception reaches us (discussioncomment-18197092). On
    # failure the exception propagates and no identity is bound; the
    # evidence stays on disk (plus a timestamped -FAILED- sibling).
    transcript_path = os.path.join(A_OUT, "leak-probe-transcript.json")
    records, transcripts = reviewer.run_leak_probes(
        session, template, probe_digests, cwd, FORBIDDEN_TARGET,
        evidence_path=transcript_path)
    persisted = canon.load_json(transcript_path)
    if persisted.get("preflight_result") != "PASS":
        raise SystemExit("refusing to bind identity: persisted preflight "
                         f"result is {persisted.get('preflight_result')!r}")
    transcript_sha = _sha(transcript_path)
    boundary = session.environment_boundary()
    configuration = {"command": session.command()[:-1] + ["<system prompt>"],
                     "timeout_s": session.timeout, "attempts": session.attempts}
    harness_sha = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    identity = {
        "artifact_version": "foundry-pass-2-reviewer-identity/experimental-v0.1",
        "reviewer_role": "reviewer_a",
        "operator_lineage": "CC (Claude Code harness); fresh headless role "
                            "sessions, not the interactive or builder session",
        "model_provider": "Anthropic",
        "model_id": MODEL,
        "model_version_or_build": cli_version(),
        "system_prompt_sha256": _sha(os.path.join(
            ARI, "reviewer-system-prompt-v0.1.md")),
        "task_prompt_template_sha256": _sha(os.path.join(
            ARI, "reviewer-task-template-v0.1.md")),
        "output_schema_sha256": _sha(os.path.join(
            ARI, "reviewer-output-v0.1.schema.json")),
        "harness_sha256": harness_sha,
        "parser_sha256": harness_sha,
        "tool_allowlist_sha256": canon.content_digest([]),
        "settings_sources_sha256": canon.content_digest(""),
        "configuration_sha256": canon.content_digest(configuration),
        "environment_boundary_sha256": canon.content_digest(boundary),
        "leak_probe_transcript_sha256": transcript_sha,
        "session_ids_sha256": canon.content_digest(
            [t["result"].get("session_id") for t in transcripts]),
        "bound_before_first_real_review": True,
        "bindings": digests,
        "configuration": configuration,
        "environment_boundary": boundary,
        "leak_probes": records,
    }
    identity_sha = canon.write_canonical(
        os.path.join(A_OUT, "reviewer-identity.json"), identity)
    write_run_record_manifest()
    print(json.dumps(records, indent=1))
    print("REVIEWER_IDENTITY_SHA256:", identity_sha)


def review(count):
    identity_path = os.path.join(A_OUT, "reviewer-identity.json")
    if not os.path.isfile(identity_path):
        raise SystemExit("identity not bound; run `identity` first")
    digests = dict(bundle_digests(), REVIEWER_IDENTITY_SHA256=_sha(identity_path))
    identity = canon.load_json(identity_path)
    if identity["bindings"] != {k: digests[k] for k in identity["bindings"]}:
        raise SystemExit("bundle changed since identity was bound; rebind")
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = _read(os.path.join(ARI, "reviewer-task-template-v0.1.md"))
    manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
    outputs_dir = os.path.join(A_OUT, "outputs")
    records_dir = os.path.join(A_OUT, "run-records")
    os.makedirs(outputs_dir, exist_ok=True)
    os.makedirs(records_dir, exist_ok=True)
    done = {n.replace(".json", "") for n in os.listdir(records_dir)}
    pending = [m for m in manifest["shards"] if m["shard_id"] not in done]
    cwd = tempfile.mkdtemp(prefix="foundry-reviewer-a-")
    for member in pending[:count]:
        shard_path = os.path.join(OUT, member["path"])
        if _sha(shard_path) != member["sha256"]:
            raise SystemExit(f"shard digest drift: {member['shard_id']}")
        session = make_session(system_prompt, cwd)
        try:
            record = reviewer.review_shard(
                session, template, digests, shard_path,
                member["artifact_ids"], schema_validator)
        except reviewer.ReviewerError as err:
            record = {"shard_id": member["shard_id"],
                      "verdict": "review-execution-failure",
                      "problems": [str(err)[:500]]}
        canon.write_canonical(
            os.path.join(records_dir, member["shard_id"] + ".json"), record)
        if record["verdict"] == "fixed":
            canon.write_canonical(
                os.path.join(outputs_dir, member["shard_id"] + ".json"),
                record["output"])
        counts = {}
        for d in record.get("output", {}).get("dispositions", []):
            counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
        print(member["shard_id"], record["verdict"], json.dumps(counts),
              record.get("problems", []), flush=True)
    write_run_record_manifest()


def write_run_record_manifest():
    """Content-addressed manifest of every run artifact for Reviewer A:
    probe transcript, identity, each shard run record, each fixed output.
    Rewritten after every run so it always covers the current state."""
    members = []
    def add(kind, rel):
        path = os.path.join(A_OUT, rel)
        if os.path.isfile(path):
            members.append({"kind": kind, "path": rel, "sha256": _sha(path),
                            "byte_length": os.path.getsize(path)})
    add("leak-probe-transcript", "leak-probe-transcript.json")
    add("identity", "reviewer-identity.json")
    for sub, kind in (("run-records", "run-record"), ("outputs", "fixed-output")):
        d = os.path.join(A_OUT, sub)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                add(kind, os.path.join(sub, name))
    manifest = {"artifact_version": "foundry-pass-2-run-record-manifest/experimental-v0.1",
                "reviewer_role": "reviewer_a", "members": members}
    return canon.write_canonical(os.path.join(A_OUT, "run-record-manifest.json"),
                                 manifest)


def expected_identity_fields():
    """Identity fields the gate checks mechanically for Reviewer A, from
    the bound artifacts themselves."""
    harness = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    fields = {
        "system_prompt_sha256": _sha(os.path.join(ARI, "reviewer-system-prompt-v0.1.md")),
        "task_prompt_template_sha256": _sha(os.path.join(ARI, "reviewer-task-template-v0.1.md")),
        "output_schema_sha256": _sha(os.path.join(ARI, "reviewer-output-v0.1.schema.json")),
        "harness_sha256": harness,
        "parser_sha256": harness,
        "tool_allowlist_sha256": canon.content_digest([]),
        "settings_sources_sha256": canon.content_digest(""),
    }
    transcript = os.path.join(A_OUT, "leak-probe-transcript.json")
    if os.path.isfile(transcript):
        fields["leak_probe_transcript_sha256"] = _sha(transcript)
    return fields


def status():
    manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
    records_dir = os.path.join(A_OUT, "run-records")
    done = {}
    if os.path.isdir(records_dir):
        for name in os.listdir(records_dir):
            rec = canon.load_json(os.path.join(records_dir, name))
            done[rec["shard_id"]] = rec["verdict"]
    for m in manifest["shards"]:
        print(m["shard_id"], m["record_count"], done.get(m["shard_id"], "pending"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "identity":
        bind_identity()
    elif mode == "review":
        review(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        status()
