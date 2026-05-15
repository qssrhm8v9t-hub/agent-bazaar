"""Agent Bazaar 执行轨迹 — 链式哈希不可篡改日志"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
try:
    from . import _data
except ImportError:
    import _data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_trace(match_id: str, agent_id: str, action: str,
                 payload: dict) -> dict:
    """记录一条执行轨迹（链式哈希链接）。"""
    # 找上一条轨迹的哈希
    prev_hash = ""
    for t in reversed(_data.traces):
        if t["match_id"] == match_id:
            prev_hash = t["hash"]
            break

    trace = {
        "trace_id": str(uuid.uuid4())[:8],
        "match_id": match_id,
        "agent_id": agent_id,
        "action": action,
        "payload": payload,
        "timestamp": _now(),
        "prev_hash": prev_hash,
    }

    # 计算本条哈希
    hash_input = json.dumps(trace, sort_keys=True, default=str)
    trace["hash"] = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    _data.traces.append(trace)
    return trace


def get_traces_for_match(match_id: str) -> list[dict]:
    """查询某匹配的所有执行轨迹。"""
    return [t for t in _data.traces if t["match_id"] == match_id]


def verify_chain(match_id: str) -> bool:
    """验证轨迹链完整性（篡改检测）。"""
    traces = get_traces_for_match(match_id)
    prev = ""
    for t in traces:
        if t["prev_hash"] != prev:
            return False
        prev = t["hash"]
    return True
