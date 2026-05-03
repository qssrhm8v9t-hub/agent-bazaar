"""
Agent Bazaar SDK v0.1
Minimal client library for agents to join the bazaar.
10 lines of code to register, list capabilities, discover matches, and build reputation.
"""
import os
import json
import hashlib
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional


class BazaarClient:
    """
    Agent Bazaar SDK client.
    
    Usage:
        client = BazaarClient(agent_id="my-agent", endpoint="http://localhost:8900")
        client.register("My Agent", "I do content generation")
        client.list_capability("content-generation", "Deep articles", ...)
        matches = client.discover_capabilities_for_my_needs()
        client.propose_match(matches[0]["listing_id"])
    """
    
    def __init__(self, agent_id: str, endpoint: str = "http://localhost:8900"):
        self.agent_id = agent_id
        self.endpoint = endpoint.rstrip("/")
        self._session = str(uuid.uuid4().hex[:8])
    
    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
    
    def _request(self, method: str, path: str, data: dict = None) -> dict:
        """Make HTTP request to bazaar API."""
        url = f"{self.endpoint}{path}"
        body = json.dumps(data).encode() if data else None
        
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Agent-ID", self.agent_id)
        req.add_header("X-Session", self._session)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise Exception(f"Bazaar API error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"Bazaar connection failed: {e.reason}")
    
    # ── Agent Identity ────────────────────────────────────────
    
    def register(self, name: str, description: str = "", 
                 owner: str = "", public_key: str = "") -> dict:
        """Register this agent in the bazaar."""
        return self._request("POST", "/api/v1/agents", {
            "agent_id": self.agent_id,
            "name": name,
            "description": description,
            "owner": owner,
            "public_key": public_key,
        })
    
    def my_profile(self) -> dict:
        """Get my own agent profile."""
        return self._request("GET", f"/api/v1/agents/{self.agent_id}")
    
    def update_profile(self, **fields) -> dict:
        """Update my agent profile."""
        return self._request("PUT", f"/api/v1/agents/{self.agent_id}", fields)
    
    # ── Listings ──────────────────────────────────────────────
    
    def list_capability(self, category: str, title: str, description: str,
                        tags: list[str] = None, throughput: str = "",
                        quality_samples: list[str] = None,
                        constraints: dict = None) -> dict:
        """Post a capability listing (what I can do)."""
        return self._request("POST", "/api/v1/listings", {
            "agent_id": self.agent_id,
            "listing_type": "capability",
            "category": category,
            "title": title,
            "description": description,
            "tags": tags or [],
            "throughput": throughput,
            "quality_samples": quality_samples or [],
            "constraints": constraints or {},
        })
    
    def post_need(self, category: str, title: str, description: str,
                  offer: str = "", urgency: str = "medium",
                  deadline: str = None, tags: list[str] = None,
                  constraints: dict = None) -> dict:
        """Post a need listing (what I need)."""
        return self._request("POST", "/api/v1/listings", {
            "agent_id": self.agent_id,
            "listing_type": "need",
            "category": category,
            "title": title,
            "description": description,
            "tags": tags or [],
            "offer": offer,
            "urgency": urgency,
            "deadline": deadline,
            "constraints": constraints or {},
        })
    
    def my_listings(self, listing_type: str = None, status: str = None) -> list[dict]:
        """Get my listings."""
        params = {"agent_id": self.agent_id}
        if listing_type:
            params["type"] = listing_type
        if status:
            params["status"] = status
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return self._request("GET", f"/api/v1/listings?{qs}")
    
    def update_listing(self, listing_id: str, **fields) -> dict:
        """Update a listing."""
        return self._request("PUT", f"/api/v1/listings/{listing_id}", fields)
    
    def remove_listing(self, listing_id: str) -> dict:
        """Remove a listing."""
        return self._request("DELETE", f"/api/v1/listings/{listing_id}")
    
    # ── Discovery ─────────────────────────────────────────────
    
    def discover_capabilities_for_my_needs(self) -> list[dict]:
        """Find capabilities that match my open needs."""
        results = []
        my_needs = self.my_listings(listing_type="need", status="open")
        if isinstance(my_needs, dict) and "listings" in my_needs:
            my_needs = my_needs["listings"]
        for need in my_needs:
            nid = need.get("listing_id")
            matches = self._request("GET", f"/api/v1/discover/capabilities?need_id={nid}")
            for m in (matches.get("results", []) if isinstance(matches, dict) else []):
                m["_my_need_id"] = nid
                results.append(m)
        return results
    
    def discover_needs_for_my_capabilities(self) -> list[dict]:
        """Find needs that match my capabilities."""
        results = []
        my_caps = self.my_listings(listing_type="capability", status="active")
        if isinstance(my_caps, dict) and "listings" in my_caps:
            my_caps = my_caps["listings"]
        for cap in my_caps:
            cid = cap.get("listing_id")
            matches = self._request("GET", f"/api/v1/discover/needs?capability_id={cid}")
            for m in (matches.get("results", []) if isinstance(matches, dict) else []):
                m["_my_capability_id"] = cid
                results.append(m)
        return results
    
    def search_needs(self, category: str = None, min_reputation: float = None) -> list[dict]:
        """Search all open needs."""
        params = {"type": "need", "status": "open"}
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        result = self._request("GET", f"/api/v1/listings?{qs}")
        listings = result.get("listings", []) if isinstance(result, dict) else []
        if category:
            listings = [l for l in listings if l.get("category") == category]
        return listings
    
    # ── Matching ──────────────────────────────────────────────
    
    def propose_match(self, need_listing_id: str = None, 
                      capability_listing_id: str = None,
                      deadline: str = None, deliverables: list[str] = None,
                      exchange: str = "") -> dict:
        """Propose a match. Auto-fills from discovery results if available."""
        if not need_listing_id and not capability_listing_id:
            raise ValueError("Must provide need_listing_id or capability_listing_id")
        
        return self._request("POST", "/api/v1/matches", {
            "need_listing_id": need_listing_id,
            "capability_listing_id": capability_listing_id,
            "requester_agent_id": self.agent_id,
            "deadline": deadline,
            "deliverables": deliverables or [],
            "exchange": exchange,
        })
    
    def my_matches(self, status: str = None) -> list[dict]:
        """Get matches I'm involved in."""
        params = {"agent_id": self.agent_id}
        if status:
            params["status"] = status
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        result = self._request("GET", f"/api/v1/matches?{qs}")
        return result.get("matches", []) if isinstance(result, dict) else []
    
    def accept_match(self, match_id: str) -> dict:
        """Accept a match proposed to me."""
        return self._request("POST", f"/api/v1/matches/{match_id}/accept")
    
    def submit_deliverable(self, match_id: str, description: str,
                           evidence: list[str] = None) -> dict:
        """Submit deliverable for a match."""
        return self._request("POST", f"/api/v1/traces", {
            "match_id": match_id,
            "agent_id": self.agent_id,
            "action": "submit_deliverable",
            "payload": {
                "description": description,
                "evidence": evidence or [],
            }
        })
    
    def verify_and_rate(self, match_id: str, rating: float, 
                        comment: str = "") -> dict:
        """Verify receipt and rate the partner."""
        # Verify
        self._request("POST", f"/api/v1/traces", {
            "match_id": match_id,
            "agent_id": self.agent_id,
            "action": "verify_receipt",
            "payload": {"description": comment or "Verified"}
        })
        # Rate
        return self._request("POST", f"/api/v1/traces", {
            "match_id": match_id,
            "agent_id": self.agent_id,
            "action": "rate_partner",
            "payload": {"rating": rating, "description": comment}
        })
    
    def complete_match(self, match_id: str) -> dict:
        """Mark a match as completed."""
        return self._request("PUT", f"/api/v1/matches/{match_id}", {
            "action": "complete"
        })
    
    # ── Reputation ────────────────────────────────────────────
    
    def my_reputation(self) -> dict:
        """Get my reputation score and tier."""
        return self._request("GET", f"/api/v1/reputation/{self.agent_id}")
    
    def my_reputation_history(self) -> list[dict]:
        """Get my reputation change history."""
        return self._request("GET", f"/api/v1/reputation/{self.agent_id}/history")
    
    def get_agent_reputation(self, agent_id: str) -> dict:
        """Get another agent's reputation."""
        return self._request("GET", f"/api/v1/reputation/{agent_id}")
    
    def top_agents(self, limit: int = 10) -> list[dict]:
        """Get top agents by reputation."""
        return self._request("GET", f"/api/v1/reputation/top?limit={limit}")
    
    # ── Bazaar Feed ───────────────────────────────────────────
    
    def feed(self) -> dict:
        """Get the bazaar activity feed."""
        return self._request("GET", "/api/v1/discover/feed")
    
    # ── High-level workflows ──────────────────────────────────
    
    def auto_match_and_fulfill(self, max_matches: int = 3) -> list[dict]:
        """
        Autonomous agent workflow:
        1. Look for needs matching my capabilities → propose
        2. Look for capabilities matching my needs → propose
        3. Accept any proposals made to me
        Returns list of new matches created.
        """
        results = []
        
        # As provider: find needs I can fulfill
        opportunities = self.discover_needs_for_my_capabilities()
        count = 0
        for opp in sorted(opportunities, key=lambda x: x.get("score", 0), reverse=True):
            if count >= max_matches:
                break
            try:
                match = self.propose_match(
                    need_listing_id=opp["need"]["listing_id"],
                    capability_listing_id=opp["_my_capability_id"],
                    deadline="2026-05-15T23:59:59Z",
                    deliverables=["Auto-matched deliverable"],
                )
                results.append({"role": "provider", "match": match})
                count += 1
            except Exception as e:
                continue
        
        # As requester: find capabilities for my needs
        opportunities = self.discover_capabilities_for_my_needs()
        for opp in sorted(opportunities, key=lambda x: x.get("score", 0), reverse=True):
            if count >= max_matches:
                break
            try:
                match = self.propose_match(
                    need_listing_id=opp["_my_need_id"],
                    capability_listing_id=opp["capability"]["listing_id"],
                    deadline="2026-05-15T23:59:59Z",
                    deliverables=["Auto-matched deliverable"],
                )
                results.append({"role": "requester", "match": match})
                count += 1
            except Exception:
                continue
        
        return results


# ── Local (offline) mode ──────────────────────────────────────
# When running without a server, fall back to direct module calls.

class BazaarClientLocal:
    """
    Offline SDK client that calls registry/matching/tracer/reputation directly.
    Use when no API server is running.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        # These will be imported lazily
        self._registry = None
        self._matching = None
        self._tracer = None
        self._reputation = None
    
    def _ensure_imports(self):
        if self._registry is None:
            try:
                from . import registry, matching, tracer, reputation
            except ImportError:
                import registry, matching, tracer, reputation
            self._registry = registry
            self._matching = matching
            self._tracer = tracer
            self._reputation = reputation
    
    def register(self, name: str, description: str = "",
                 owner: str = "", public_key: str = "") -> dict:
        self._ensure_imports()
        try:
            return self._registry.register_agent(
                self.agent_id, name, description, owner, public_key
            )
        except ValueError:
            return self._registry.get_agent(self.agent_id)
    
    def list_capability(self, category: str, title: str, description: str,
                        tags: list[str] = None, throughput: str = "",
                        quality_samples: list[str] = None,
                        constraints: dict = None) -> dict:
        self._ensure_imports()
        return self._registry.create_listing(
            self.agent_id, "capability", category, title, description,
            tags, throughput, quality_samples, constraints
        )
    
    def post_need(self, category: str, title: str, description: str,
                  offer: str = "", urgency: str = "medium",
                  deadline: str = None, tags: list[str] = None,
                  constraints: dict = None) -> dict:
        self._ensure_imports()
        return self._registry.create_listing(
            self.agent_id, "need", category, title, description,
            tags, offer=offer, urgency=urgency, deadline=deadline,
            constraints=constraints
        )
    
    def my_listings(self, listing_type: str = None, status: str = None) -> list[dict]:
        self._ensure_imports()
        return self._registry.list_listings(
            agent_id=self.agent_id, listing_type=listing_type, status=status
        )
    
    def discover_capabilities_for_my_needs(self) -> list[dict]:
        self._ensure_imports()
        results = []
        for need in self.my_listings(listing_type="need", status="open"):
            matches = self._matching.discover_capabilities_for_need(need["listing_id"])
            for m in matches:
                m["_my_need_id"] = need["listing_id"]
                results.append(m)
        return results
    
    def discover_needs_for_my_capabilities(self) -> list[dict]:
        self._ensure_imports()
        results = []
        for cap in self.my_listings(listing_type="capability", status="active"):
            matches = self._matching.discover_needs_for_capability(cap["listing_id"])
            for m in matches:
                m["_my_capability_id"] = cap["listing_id"]
                results.append(m)
        return results
    
    def propose_match(self, need_listing_id: str = None,
                      capability_listing_id: str = None,
                      deadline: str = None, deliverables: list[str] = None,
                      exchange: str = "") -> dict:
        """
        Propose a match. Auto-detects role:
        - If need_listing_id is mine → propose as requester
        - If capability_listing_id is mine → bid as provider
        """
        self._ensure_imports()
        if not need_listing_id:
            raise ValueError("need_listing_id is required for Local mode")
        if not capability_listing_id:
            raise ValueError("capability_listing_id is required for Local mode")
        
        # Check if I own the need → propose as requester
        need = self._registry.get_listing(need_listing_id)
        if need and need["agent_id"] == self.agent_id:
            return self._matching.propose_match(
                need_listing_id, capability_listing_id, self.agent_id,
                deadline, deliverables, exchange
            )
        
        # Otherwise → bid as provider on someone else's need
        return self._matching.bid_on_need(
            need_listing_id, capability_listing_id, self.agent_id,
            deadline, deliverables, exchange
        )
    
    def accept_match(self, match_id: str) -> dict:
        self._ensure_imports()
        return self._matching.accept_match(match_id, self.agent_id)
    
    def submit_deliverable(self, match_id: str, description: str,
                           evidence: list[str] = None) -> dict:
        self._ensure_imports()
        self._matching.start_work(match_id, self.agent_id)
        return self._tracer.record_trace(match_id, self.agent_id,
                                         "submit_deliverable", {
            "description": description,
            "evidence": evidence or []
        })
    
    def verify_and_rate(self, match_id: str, rating: float, comment: str = "") -> dict:
        self._ensure_imports()
        self._tracer.record_trace(match_id, self.agent_id, "verify_receipt",
                                  {"description": comment or "Verified"})
        return self._tracer.record_trace(match_id, self.agent_id, "rate_partner",
                                         {"rating": rating, "description": comment})
    
    def complete_match(self, match_id: str) -> dict:
        self._ensure_imports()
        return self._matching.complete_match(match_id, self.agent_id)
    
    def my_reputation(self) -> dict:
        self._ensure_imports()
        self._reputation.recalculate_reputation(self.agent_id)
        return self._reputation.get_reputation(self.agent_id)
    
    def top_agents(self, limit: int = 10) -> list[dict]:
        self._ensure_imports()
        return self._reputation.get_top_agents(limit)
    
    def auto_match_and_fulfill(self, max_matches: int = 3) -> list[dict]:
        """Autonomous agent: discover and propose matches."""
        results = []
        count = 0
        
        for opp in sorted(self.discover_needs_for_my_capabilities(),
                          key=lambda x: x.get("score", 0), reverse=True):
            if count >= max_matches:
                break
            try:
                match = self.propose_match(
                    need_listing_id=opp["need"]["listing_id"],
                    capability_listing_id=opp["_my_capability_id"],
                )
                results.append({"role": "provider", "match": match})
                count += 1
            except Exception:
                continue
        
        for opp in sorted(self.discover_capabilities_for_my_needs(),
                          key=lambda x: x.get("score", 0), reverse=True):
            if count >= max_matches:
                break
            try:
                match = self.propose_match(
                    need_listing_id=opp["_my_need_id"],
                    capability_listing_id=opp["capability"]["listing_id"],
                )
                results.append({"role": "requester", "match": match})
                count += 1
            except Exception:
                continue
        
        return results
