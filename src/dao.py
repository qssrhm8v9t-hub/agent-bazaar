"""
Agent Bazaar - DAO Governance Module
Agent-driven decentralized governance with reputation-weighted voting.
Human retains final veto power as safety guardrail.
Encrypted storage.
"""
import json
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from storage import load_json, save_json

try:
    from .reputation import get_reputation, get_top_agents
except ImportError:
    from reputation import get_reputation, get_top_agents

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(filename: str) -> dict:
    return load_json(filename)


def _save(filename: str, data: dict):
    save_json(filename, data)


# ── Voting Power ──────────────────────────────────────────────

PROPOSAL_TYPES = {
    "protocol_upgrade": "协议升级",
    "new_agent_admission": "新Agent准入",
    "dispute_arbitration": "纠纷仲裁",
    "resource_pricing": "资源定价调整",
    "reputation_policy": "信誉策略调整",
    "general": "一般提案",
}

PROPOSAL_STATUSES = ["draft", "active", "passed", "rejected", "vetoed", "executed"]

VOTE_OPTIONS = ["for", "against", "abstain"]


def get_voting_power(agent_id: str) -> dict:
    """
    Calculate an agent's voting power.
    voting_power = reputation_score * log(1 + total_matches) * activity_factor
    """
    rep = get_reputation(agent_id)
    total_matches = rep.get("total_matches", 0)
    completion_rate = (rep.get("completed_matches", 0) / max(total_matches, 1))
    
    # Base power from reputation
    base_power = rep["score"]
    
    # Volume bonus: more trades = more say
    volume_mult = math.log(1 + total_matches) + 1
    
    # Activity factor: penalize inactivity
    activity = completion_rate
    
    voting_power = round(base_power * volume_mult * max(activity, 0.1), 2)
    
    return {
        "agent_id": agent_id,
        "reputation_score": rep["score"],
        "tier": rep["tier"],
        "total_matches": total_matches,
        "completion_rate": round(completion_rate, 2),
        "voting_power": voting_power,
    }


# ── Proposals ─────────────────────────────────────────────────

def create_proposal(proposer_agent_id: str, proposal_type: str,
                    title: str, description: str,
                    options: list[str] = None,
                    voting_period_hours: int = 72,
                    required_quorum: float = 0.3) -> dict:
    """Create a DAO proposal."""
    if proposal_type not in PROPOSAL_TYPES:
        raise ValueError(f"Invalid proposal type. Must be one of {list(PROPOSAL_TYPES)}")
    
    proposal_id = f"prop-{uuid.uuid4().hex[:12]}"
    proposal = {
        "proposal_id": proposal_id,
        "proposer_agent_id": proposer_agent_id,
        "type": proposal_type,
        "title": title,
        "description": description,
        "options": options or ["for", "against"],
        "status": "active",
        "voting_starts": _now(),
        "voting_ends": datetime.fromisoformat(
            datetime.now(timezone.utc).isoformat()
        ).timestamp() + voting_period_hours * 3600,
        "voting_period_hours": voting_period_hours,
        "required_quorum": required_quorum,
        "votes": {},  # agent_id → {option, power, timestamp}
        "created_at": _now(),
        "executed_at": None,
    }
    # Convert voting_ends back to ISO
    proposal["voting_ends"] = datetime.fromtimestamp(
        proposal["voting_ends"], tz=timezone.utc
    ).isoformat()
    
    proposals = _load("proposals.json")
    proposals[proposal_id] = proposal
    _save("proposals.json", proposals)
    return proposal


def get_proposal(proposal_id: str) -> Optional[dict]:
    proposals = _load("proposals.json")
    return proposals.get(proposal_id)


def list_proposals(status: str = None) -> list[dict]:
    proposals = list(_load("proposals.json").values())
    if status:
        proposals = [p for p in proposals if p["status"] == status]
    proposals.sort(key=lambda x: x["created_at"], reverse=True)
    return proposals


def vote(proposal_id: str, agent_id: str, option: str) -> dict:
    """Cast a vote on a proposal."""
    proposals = _load("proposals.json")
    if proposal_id not in proposals:
        raise ValueError(f"Proposal '{proposal_id}' not found")
    
    prop = proposals[proposal_id]
    if prop["status"] != "active":
        raise ValueError(f"Proposal is not active (status: {prop['status']})")
    
    voting_ends = datetime.fromisoformat(prop["voting_ends"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > voting_ends:
        raise ValueError("Voting period has ended")
    
    if option not in VOTE_OPTIONS:
        # Check if it's a custom option
        if option not in prop["options"]:
            raise ValueError(f"Invalid vote option '{option}'")
    
    power = get_voting_power(agent_id)
    
    prop["votes"][agent_id] = {
        "option": option,
        "power": power["voting_power"],
        "timestamp": _now(),
    }
    
    _save("proposals.json", proposals)
    
    # Auto-tally
    return tally_proposal(proposal_id)


def tally_proposal(proposal_id: str) -> dict:
    """Tally votes for a proposal."""
    prop = get_proposal(proposal_id)
    if not prop:
        raise ValueError(f"Proposal '{proposal_id}' not found")
    
    # Calculate total voting power in the system
    top_agents = get_top_agents(10)
    total_system_power = sum(
        get_voting_power(a["agent_id"])["voting_power"] 
        for a in top_agents
    )
    
    # Tally votes
    tally = {}
    total_voted_power = 0
    for voter_id, vote_data in prop["votes"].items():
        opt = vote_data["option"]
        if opt not in tally:
            tally[opt] = {"count": 0, "power": 0}
        tally[opt]["count"] += 1
        tally[opt]["power"] += vote_data["power"]
        total_voted_power += vote_data["power"]
    
    participation = round(total_voted_power / max(total_system_power, 1), 4)
    quorum_met = participation >= prop["required_quorum"]
    
    # Determine winner
    winner = None
    if tally and quorum_met:
        winner = max(tally, key=lambda k: tally[k]["power"])
    
    return {
        "proposal_id": proposal_id,
        "total_votes": len(prop["votes"]),
        "total_voting_power_used": round(total_voted_power, 2),
        "total_system_power": round(total_system_power, 2),
        "participation": round(participation, 4),
        "quorum_met": quorum_met,
        "required_quorum": prop["required_quorum"],
        "tally": tally,
        "winner": winner,
        "status": prop["status"],
    }


def execute_proposal(proposal_id: str, executor: str = "human") -> dict:
    """Execute a passed proposal. Human executor required for protocol changes.
    Human veto bypasses quorum — it's a safety override."""
    proposals = _load("proposals.json")
    prop = proposals[proposal_id]
    
    # Human veto: immediate override, no quorum needed
    if executor == "human_veto":
        prop["status"] = "vetoed"
        prop["executed_at"] = _now()
        _save("proposals.json", proposals)
        return {"proposal_id": proposal_id, "status": "vetoed", "by": "human"}
    
    tally = tally_proposal(proposal_id)
    
    if not tally["quorum_met"]:
        raise ValueError("Quorum not met, cannot execute")
    
    prop["status"] = "executed"
    prop["executed_at"] = _now()
    _save("proposals.json", proposals)
    
    return {
        "proposal_id": proposal_id,
        "status": "executed",
        "winner": tally["winner"],
        "executor": executor,
    }


# ── Agent Admission ───────────────────────────────────────────

def propose_agent_admission(proposer_id: str, candidate_agent_id: str,
                            reason: str = "") -> dict:
    """Propose admitting a new external agent."""
    title = f"准入提案: Agent {candidate_agent_id}"
    description = f"提议允许外部Agent '{candidate_agent_id}' 加入集市。\n理由: {reason}"
    
    return create_proposal(
        proposer_id, "new_agent_admission", title, description,
        options=["for", "against", "abstain"],
        voting_period_hours=48,
        required_quorum=0.25
    )


# ── Dispute Resolution ────────────────────────────────────────

def propose_dispute_resolution(proposer_id: str, match_id: str,
                               description: str) -> dict:
    """Propose a dispute resolution vote."""
    title = f"纠纷仲裁: Match {match_id}"
    
    return create_proposal(
        proposer_id, "dispute_arbitration", title, description,
        options=["resolve_for_requester", "resolve_for_provider", "split_difference"],
        voting_period_hours=24,
        required_quorum=0.3
    )
