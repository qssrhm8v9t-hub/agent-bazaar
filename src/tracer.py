"""
Agent Bazaar - Execution Trace Recorder
Append-only hash-chained execution traces. Each trace links to the previous
one in the same match chain via SHA-256, creating tamper-evident evidence.

Storage: encrypted JSONL via EncryptedJSONL handler.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import EncryptedJSONL

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
TRACES_FILE = "traces.jsonl"

VALID_ACTIONS = {
    "accept_match", "submit_deliverable", "verify_receipt",
    "rate_partner", "dispute", "resolve_dispute"
}

_traces_handler = None


def _get_handler() -> EncryptedJSONL:
    global _traces_handler
    if _traces_handler is None:
        _traces_handler = EncryptedJSONL(TRACES_FILE)
    return _traces_handler


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_hash(record: dict) -> str:
    """Compute SHA-256 hash of a trace record (excluding the hash field itself)."""
    copy = {k: v for k, v in record.items() if k != "hash"}
    canonical = json.dumps(copy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _get_prev_hash(match_id: str) -> str:
    """Get the hash of the most recent trace for a given match."""
    handler = _get_handler()
    all_traces = handler.read_all()
    for trace in reversed(all_traces):
        if trace.get("match_id") == match_id:
            return trace.get("hash", "0" * 64)
    return "0" * 64


def record_trace(
    match_id: str,
    agent_id: str,
    action: str,
    payload: dict = None,
) -> dict:
    """
    Record an execution trace. Appends to encrypted traces.jsonl.

    Args:
        match_id: The match this trace belongs to
        agent_id: The agent performing this action
        action: One of VALID_ACTIONS
        payload: Action-specific data (description, evidence, rating, etc.)
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Must be one of {VALID_ACTIONS}")

    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    prev_hash = _get_prev_hash(match_id)

    trace = {
        "trace_id": trace_id,
        "match_id": match_id,
        "agent_id": agent_id,
        "action": action,
        "payload": payload or {},
        "timestamp": _now(),
        "prev_hash": prev_hash,
    }

    trace["hash"] = _compute_hash(trace)

    handler = _get_handler()
    handler.append(trace)

    return trace


def get_traces_for_match(match_id: str) -> list[dict]:
    """Get all traces for a specific match, in chronological order."""
    all_traces = _get_handler().read_all()
    return [t for t in all_traces if t.get("match_id") == match_id]


def get_traces_for_agent(agent_id: str, limit: int = 50) -> list[dict]:
    """Get recent traces by a specific agent."""
    all_traces = _get_handler().read_all()
    agent_traces = [t for t in all_traces if t.get("agent_id") == agent_id]
    return agent_traces[-limit:]


def verify_trace(trace_id: str) -> dict:
    """
    Verify the integrity of a specific trace and its chain.
    Returns {valid, trace, chain_check}.
    """
    all_traces = _get_handler().read_all()
    if not all_traces:
        return {"valid": False, "error": "No traces found"}

    target_trace = None
    for trace in all_traces:
        if trace.get("trace_id") == trace_id:
            target_trace = trace
            break

    if not target_trace:
        return {"valid": False, "error": f"Trace '{trace_id}' not found"}

    # Verify this trace's own hash
    expected_hash = _compute_hash(target_trace)
    hash_ok = expected_hash == target_trace.get("hash", "")

    # Verify the chain for this match
    match_traces = [t for t in all_traces if t.get("match_id") == target_trace["match_id"]]
    chain_ok = True
    for i, t in enumerate(match_traces):
        if i == 0:
            expected_prev = "0" * 64
        else:
            expected_prev = match_traces[i - 1].get("hash", "")
        if t.get("prev_hash") != expected_prev:
            chain_ok = False
            break

    return {
        "valid": hash_ok and chain_ok,
        "trace": target_trace,
        "hash_ok": hash_ok,
        "chain_ok": chain_ok,
    }


def verify_match_chain(match_id: str) -> dict:
    """Verify the entire trace chain for a match."""
    traces = get_traces_for_match(match_id)
    if not traces:
        return {"valid": True, "traces": 0, "message": "No traces for this match"}

    for i, trace in enumerate(traces):
        # Verify own hash
        expected = _compute_hash(trace)
        if expected != trace.get("hash", ""):
            return {"valid": False, "broken_at": i,
                    "trace_id": trace["trace_id"],
                    "error": "Hash mismatch"}

        # Verify prev_hash links
        if i == 0:
            expected_prev = "0" * 64
        else:
            expected_prev = traces[i - 1]["hash"]
        if trace.get("prev_hash") != expected_prev:
            return {"valid": False, "broken_at": i,
                    "trace_id": trace["trace_id"],
                    "error": "Chain link broken"}

    return {"valid": True, "traces": len(traces)}


def get_all_traces(limit: int = 100) -> list[dict]:
    """Get the most recent traces across all matches."""
    all_traces = _get_handler().read_all()
    return all_traces[-limit:]
