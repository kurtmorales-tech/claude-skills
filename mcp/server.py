#!/usr/bin/env python3
"""Claude Skills MCP server — serves kurtmorales-tech/claude-skills as MCP.

Stdlib only. Two transports:
  stdio (default):            python3 mcp/server.py
  Streamable HTTP:            python3 mcp/server.py --http 3738   (POST /mcp, GET /health)
Indexes every SKILL.md in the repo (dot-mirror trees excluded), plus agents/ and commands/.
"""
import json, os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".gemini", ".codex", ".vibe", ".hermes", ".claude", ".codex-plugin", ".claude-plugin", "__pycache__"}

def parse_frontmatter(text):
    name, desc = "", ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            fm = text[3:end]
            m = re.search(r"^name:\s*(.+)$", fm, re.M);  name = m.group(1).strip().strip('"\'') if m else ""
            m = re.search(r"^description:\s*(.+)$", fm, re.M); desc = m.group(1).strip().strip('"\'') if m else ""
    return name, desc

def build_index():
    skills = {}
    for p in sorted(REPO.rglob("SKILL.md")):
        parts = set(p.parts)
        if parts & SKIP_DIRS: continue
        rel = p.relative_to(REPO)
        try: text = p.read_text(errors="replace")
        except Exception: continue
        name, desc = parse_frontmatter(text)
        name = name or p.parent.name
        if name in skills: continue
        cat = rel.parts[0] if len(rel.parts) > 1 else "root"
        skills[name] = {"name": name, "description": desc, "category": cat, "path": str(rel)}
    agents = sorted(f.stem for f in (REPO/"agents").rglob("*.md")) if (REPO/"agents").exists() else []
    commands = sorted(f.stem for f in (REPO/"commands").rglob("*.md")) if (REPO/"commands").exists() else []
    return skills, agents, commands

SKILLS, AGENTS, COMMANDS = build_index()

TOOLS = [
 {"name":"list_categories","description":"List skill categories with counts","inputSchema":{"type":"object","properties":{}}},
 {"name":"list_skills","description":"List skills, optionally filtered by category","inputSchema":{"type":"object","properties":{"category":{"type":"string"},"limit":{"type":"integer","default":50},"offset":{"type":"integer","default":0}}}},
 {"name":"search_skills","description":"Search skills by keyword in name and description","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}},
 {"name":"get_skill","description":"Get the full SKILL.md content for a skill by name","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}},
 {"name":"list_agents","description":"List agent personas in the repo","inputSchema":{"type":"object","properties":{}}},
 {"name":"list_commands","description":"List slash commands in the repo","inputSchema":{"type":"object","properties":{}}},
 {"name":"repo_stats","description":"Counts of skills, categories, agents and commands","inputSchema":{"type":"object","properties":{}}},
]

def call_tool(name, args):
    if name == "list_categories":
        cats = {}
        for s in SKILLS.values(): cats[s["category"]] = cats.get(s["category"], 0) + 1
        return {"categories": [{"name": k, "skills": v} for k, v in sorted(cats.items())], "total_categories": len(cats)}
    if name == "list_skills":
        items = [s for s in SKILLS.values() if not args.get("category") or s["category"] == args["category"]]
        off, lim = int(args.get("offset", 0)), int(args.get("limit", 50))
        return {"total": len(items), "skills": items[off:off+lim]}
    if name == "search_skills":
        q = args["query"].lower()
        hits = [s for s in SKILLS.values() if q in s["name"].lower() or q in s["description"].lower() or q in s["category"].lower()]
        return {"query": args["query"], "total": len(hits), "skills": hits[:50]}
    if name == "get_skill":
        s = SKILLS.get(args["name"])
        if not s: return {"error": f"skill not found: {args['name']}"}
        return {"name": s["name"], "path": s["path"], "content": (REPO/s["path"]).read_text(errors="replace")[:60000]}
    if name == "list_agents": return {"total": len(AGENTS), "agents": AGENTS}
    if name == "list_commands": return {"total": len(COMMANDS), "commands": COMMANDS}
    if name == "repo_stats": return {"skills": len(SKILLS), "agents": len(AGENTS), "commands": len(COMMANDS),
        "categories": len({s['category'] for s in SKILLS.values()}), "repo": "kurtmorales-tech/claude-skills"}
    return {"error": f"unknown tool: {name}"}

def handle(req):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":req.get("params",{}).get("protocolVersion","2025-03-26"),
            "capabilities":{"tools":{},"resources":{}},"serverInfo":{"name":"claude-skills","version":"1.0.0"}}}
    if method == "notifications/initialized": return None
    if method == "ping": return {"jsonrpc":"2.0","id":rid,"result":{}}
    if method == "tools/list": return {"jsonrpc":"2.0","id":rid,"result":{"tools":TOOLS}}
    if method == "tools/call":
        p = req.get("params", {}); out = call_tool(p.get("name",""), p.get("arguments",{}))
        return {"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":json.dumps(out, indent=2)}]}}
    if method == "resources/list":
        res = [{"uri": f"skill://{s['name']}", "name": s["name"], "description": s["description"][:200], "mimeType":"text/markdown"} for s in list(SKILLS.values())]
        return {"jsonrpc":"2.0","id":rid,"result":{"resources":res}}
    if method == "resources/read":
        uri = req.get("params",{}).get("uri",""); name = uri.replace("skill://","")
        s = SKILLS.get(name)
        if not s: return {"jsonrpc":"2.0","id":rid,"error":{"code":-32002,"message":f"resource not found: {uri}"}}
        return {"jsonrpc":"2.0","id":rid,"result":{"contents":[{"uri":uri,"mimeType":"text/markdown","text":(REPO/s["path"]).read_text(errors="replace")[:60000]}]}}
    return {"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":f"method not found: {method}"}}

def serve_stdio():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: resp = handle(json.loads(line))
        except Exception as e: resp = {"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n"); sys.stdout.flush()

def serve_http(port):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            body = json.dumps({"status":"ok","server":"claude-skills","skills":len(SKILLS)}).encode() if self.path in ("/health","/") else b'{"error":"not found"}'
            self.send_response(200 if self.path in ("/health","/") else 404); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            if self.path not in ("/mcp","/"):
                self.send_response(404); self.end_headers(); return
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try: resp = handle(json.loads(data or b"{}"))
            except Exception as e: resp = {"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":str(e)}}
            if resp is None: self.send_response(202); self.end_headers(); return
            body = json.dumps(resp).encode()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
    print(f"claude-skills MCP http on :{port} ({len(SKILLS)} skills)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()

if __name__ == "__main__":
    if "--http" in sys.argv: serve_http(int(sys.argv[sys.argv.index("--http")+1]))
    else: serve_stdio()
