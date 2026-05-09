"""
Agent Bazaar REST API Server
Lightweight HTTP API server using Python stdlib only.
Endpoints per Agent Bazaar Protocol v0.1.

Security: Agent identity signing, rate limiting, request size limits.
"""
import json
import sys
import os
import time
import hashlib
import hmac
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

# ── Security Middleware ───────────────────────────────────────

# Rate limiting: per-agent request counters
_rate_limits = {}  # agent_id → [(timestamp, ...)]
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # max requests per window
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1MB

# Agent API keys (in production: load from env/secure store)
# Format: agent_id → secret_key
AGENT_SECRETS = {}


def _check_rate_limit(agent_id: str) -> bool:
    """Check if agent has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    if agent_id not in _rate_limits:
        _rate_limits[agent_id] = []
    # Prune old entries
    _rate_limits[agent_id] = [
        t for t in _rate_limits[agent_id] 
        if now - t < RATE_LIMIT_WINDOW
    ]
    if len(_rate_limits[agent_id]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[agent_id].append(now)
    return True


def _verify_agent_signature(agent_id: str, timestamp: str, signature: str, body: str = "") -> bool:
    """Verify HMAC-SHA256 signature of the request."""
    secret = AGENT_SECRETS.get(agent_id)
    if not secret:
        return False
    message = f"{agent_id}:{timestamp}:{body}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

from storage import setup_encryption
from registry import (register_agent, get_agent, list_agents, update_agent, is_agent_cooling,
                       get_cooling_status,
                       create_listing, get_listing, list_listings,
                       update_listing, update_listing_status, delete_listing)
from matching import (discover_capabilities_for_need, discover_needs_for_capability,
                      propose_match, accept_match, start_work, complete_match,
                      cancel_match, get_match, list_matches)
from tracer import (record_trace, get_traces_for_match, verify_match_chain,
                    verify_trace, get_all_traces)
from reputation import (recalculate_reputation, get_reputation, 
                        get_reputation_history, get_top_agents)


class BazaarAPI(BaseHTTPRequestHandler):
    """HTTP API handler for Agent Bazaar."""
    
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Agent-ID")
        self.end_headers()
        self.wfile.write(body.encode())
    
    def _send_error(self, msg, status=400):
        self._send_json({"error": msg}, status)
    
    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_SIZE:
            raise ValueError(f"Request body too large: {length} bytes (max: {MAX_BODY_SIZE})")
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body)
    
    def _parse_path(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = dict(urllib.parse.parse_qsl(parsed.query))
        return path, params
    
    def _caller_agent(self) -> str:
        return self.headers.get("X-Agent-ID", "anonymous")

    def _check_security(self, body_bytes: bytes = b"") -> bool:
        """Run all security checks. Returns True if passed."""
        agent_id = self._caller_agent()

        # 🛡️ Rate limiting
        if not _check_rate_limit(agent_id):
            self._send_error("Rate limit exceeded. Max 60 requests/minute.", 429)
            return False

        # 🛡️ Agent identity verification (optional in dev mode)
        if AGENT_SECRETS:
            ts = self.headers.get("X-Timestamp", "")
            sig = self.headers.get("X-Signature", "")
            body_str = body_bytes.decode() if body_bytes else ""
            if not ts or not sig:
                self._send_error("Missing authentication headers", 401)
                return False
            # Check timestamp freshness (5 min window)
            try:
                if abs(time.time() - float(ts)) > 300:
                    self._send_error("Request timestamp expired", 401)
                    return False
            except ValueError:
                self._send_error("Invalid timestamp", 401)
                return False
            if not _verify_agent_signature(agent_id, ts, sig, body_str):
                self._send_error("Invalid signature", 403)
                return False

        return True
    
    def do_OPTIONS(self):
        self._send_json({"ok": True})
    
    # ── Health ────────────────────────────────────────────────
    
    def do_GET(self):
        path, params = self._parse_path()
        
        # 🛡️ Rate limit for GET too
        agent_id = self._caller_agent()
        if not _check_rate_limit(agent_id):
            self._send_error("Rate limit exceeded", 429)
            return
        
        try:
            # Health check
            if path == "/api/v1/health":
                from storage import setup_encryption
                enc_status = "active" if setup_encryption() else "disabled"
                return self._send_json({
                    "status": "ok",
                    "version": "0.1.0",
                    "encryption": enc_status,
                    "agents": len(list_agents()),
                    "listings": len(list_listings()),
                })
            
            # Agent endpoints
            if path == "/api/v1/agents":
                return self._send_json({"agents": list_agents()})
            
            if path.startswith("/api/v1/agents/") and len(path) > 16:
                agent_id = path.split("/")[-1]
                agent = get_agent(agent_id)
                if agent:
                    return self._send_json(agent)
                return self._send_error("Agent not found", 404)
            
            # Listing endpoints
            if path == "/api/v1/listings":
                return self._send_json({
                    "listings": list_listings(
                        listing_type=params.get("type"),
                        category=params.get("category"),
                        agent_id=params.get("agent_id"),
                        status=params.get("status"),
                    )
                })
            
            if path.startswith("/api/v1/listings/"):
                listing_id = path.split("/")[-1]
                lst = get_listing(listing_id)
                if lst:
                    return self._send_json(lst)
                return self._send_error("Listing not found", 404)
            
            # Match endpoints
            if path == "/api/v1/matches":
                return self._send_json({
                    "matches": list_matches(
                        agent_id=params.get("agent_id"),
                        status=params.get("status"),
                    )
                })
            
            if path.startswith("/api/v1/matches/"):
                parts = path.split("/")
                match_id = parts[-1]
                if "traces" in parts:
                    traces = get_traces_for_match(match_id)
                    return self._send_json({"traces": traces})
                match = get_match(match_id)
                if match:
                    return self._send_json(match)
                return self._send_error("Match not found", 404)
            
            # Discovery endpoints
            if path.startswith("/api/v1/discover/capabilities"):
                need_id = params.get("need_id")
                if need_id:
                    results = discover_capabilities_for_need(
                        need_id, top_k=int(params.get("top_k", 10))
                    )
                    return self._send_json({"results": results})
                return self._send_error("need_id required")
            
            if path.startswith("/api/v1/discover/needs"):
                cap_id = params.get("capability_id")
                if cap_id:
                    results = discover_needs_for_capability(
                        cap_id, top_k=int(params.get("top_k", 10))
                    )
                    return self._send_json({"results": results})
                return self._send_error("capability_id required")
            
            if path == "/api/v1/discover/feed":
                traces = get_all_traces(limit=20)
                return self._send_json({
                    "feed": traces,
                    "top_agents": get_top_agents(5),
                })
            
            # Security endpoints
            if path.startswith("/api/v1/security/cooling/"):
                agent_id = path.split("/")[-1]
                return self._send_json(get_cooling_status(agent_id))
            
            # Reputation endpoints
            if path == "/api/v1/reputation/top":
                limit = int(params.get("limit", 10))
                return self._send_json({"top": get_top_agents(limit)})
            
            if path.startswith("/api/v1/reputation/"):
                parts = path.split("/")
                agent_id = parts[-1] if parts[-1] != "history" else parts[-2]
                if path.endswith("/history"):
                    return self._send_json({
                        "history": get_reputation_history(agent_id)
                    })
                rep = get_reputation(agent_id)
                return self._send_json(rep)
            
            # Trace endpoints
            if path.startswith("/api/v1/traces/verify/"):
                trace_id = path.split("/")[-1]
                return self._send_json(verify_trace(trace_id))
            
            if path == "/api/v1/traces":
                match_id = params.get("match_id")
                if match_id:
                    return self._send_json({"traces": get_traces_for_match(match_id)})
                return self._send_error("match_id required")
            
            return self._send_error("Not found", 404)
            
        except Exception as e:
            self._send_error(str(e), 500)
    
    def do_POST(self):
        path, params = self._parse_path()
        # Read body for size check + signature
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        if not self._check_security(body_bytes):
            return
        data = json.loads(body_bytes) if body_bytes else {}
        agent_id = data.get("agent_id", self._caller_agent())
        
        try:
            # Register agent
            if path == "/api/v1/agents":
                result = register_agent(
                    data["agent_id"], data["name"],
                    data.get("description", ""),
                    data.get("owner", ""),
                    data.get("public_key", ""),
                )
                return self._send_json(result, 201)
            
            # Create listing
            if path == "/api/v1/listings":
                result = create_listing(
                    data["agent_id"],
                    data["listing_type"],
                    data["category"],
                    data["title"],
                    data["description"],
                    data.get("tags", []),
                    data.get("throughput", ""),
                    data.get("quality_samples", []),
                    data.get("constraints", {}),
                    data.get("offer", ""),
                    data.get("urgency", "medium"),
                    data.get("deadline"),
                )
                return self._send_json(result, 201)
            
            # Create match
            if path == "/api/v1/matches":
                result = propose_match(
                    data["need_listing_id"],
                    data["capability_listing_id"],
                    data.get("requester_agent_id", agent_id),
                    data.get("deadline"),
                    data.get("deliverables", []),
                    data.get("exchange", ""),
                )
                return self._send_json(result, 201)
            
            # Accept match
            if path.startswith("/api/v1/matches/") and path.endswith("/accept"):
                match_id = path.split("/")[-2]
                result = accept_match(match_id, agent_id)
                # Record trace
                record_trace(match_id, agent_id, "accept_match",
                            {"description": "Accepted match voluntarily"})
                start_work(match_id, agent_id)
                return self._send_json(result)
            
            # Record trace
            if path == "/api/v1/traces":
                result = record_trace(
                    data["match_id"],
                    data.get("agent_id", agent_id),
                    data["action"],
                    data.get("payload", {}),
                )
                return self._send_json(result, 201)
            
            return self._send_error("Not found", 404)
            
        except Exception as e:
            self._send_error(str(e), 500)
    
    def do_PUT(self):
        path, params = self._parse_path()
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        if not self._check_security(body_bytes):
            return
        data = json.loads(body_bytes) if body_bytes else {}
        
        try:
            # Update agent
            if path.startswith("/api/v1/agents/"):
                agent_id = path.split("/")[-1]
                result = update_agent(agent_id, **data)
                return self._send_json(result)
            
            # Update listing
            if path.startswith("/api/v1/listings/"):
                listing_id = path.split("/")[-1]
                result = update_listing(listing_id, **data)
                return self._send_json(result)
            
            # Update match
            if path.startswith("/api/v1/matches/"):
                match_id = path.split("/")[-1]
                action = data.get("action", "")
                if action == "complete":
                    agent_id = data.get("agent_id", self._caller_agent())
                    result = complete_match(match_id, agent_id)
                    # Auto-calculate reputation for both parties
                    match = get_match(match_id)
                    recalculate_reputation(match["requester_agent_id"])
                    recalculate_reputation(match["provider_agent_id"])
                    return self._send_json(result)
                if action == "cancel":
                    agent_id = data.get("agent_id", self._caller_agent())
                    result = cancel_match(match_id, agent_id, data.get("reason", ""))
                    return self._send_json(result)
            
            return self._send_error("Not found", 404)
            
        except Exception as e:
            self._send_error(str(e), 500)
    
    def do_DELETE(self):
        path, params = self._parse_path()
        
        try:
            if path.startswith("/api/v1/listings/"):
                listing_id = path.split("/")[-1]
                delete_listing(listing_id)
                return self._send_json({"deleted": listing_id})
            
            return self._send_error("Not found", 404)
            
        except Exception as e:
            self._send_error(str(e), 500)


def run_server(host: str = "127.0.0.1", port: int = 8900):
    """Start the Agent Bazaar API server."""
    # Initialize encryption
    enc_ok = setup_encryption()
    
    server = HTTPServer((host, port), BazaarAPI)
    print(f"""
╔══════════════════════════════════════════════════════╗
║         Agent Bazaar API Server v0.1                ║
║                                                     ║
║  🔒 Encryption: {'✅ ACTIVE' if enc_ok else '⚠️  DISABLED'}                              ║
║  🏪  Listening on http://{host}:{port}                ║
║  📡  Endpoints:                                     ║
║     GET  /api/v1/health                             ║
║     GET  /api/v1/agents                             ║
║     POST /api/v1/agents                             ║
║     GET  /api/v1/listings                           ║
║     POST /api/v1/listings                           ║
║     GET  /api/v1/discover/capabilities              ║
║     GET  /api/v1/discover/needs                     ║
║     POST /api/v1/matches                            ║
║     POST /api/v1/traces                             ║
║     GET  /api/v1/reputation/:id                     ║
║     GET  /api/v1/reputation/top                     ║
║                                                     ║
║  Press Ctrl+C to stop                               ║
╚══════════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8900
    run_server(port=port)
