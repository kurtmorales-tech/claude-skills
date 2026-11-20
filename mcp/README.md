# claude-skills as an MCP server

This repo is now an MCP server. `mcp/server.py` (Python, stdlib only, no pip installs)
indexes all 400 skills, 35 agents and 39 commands in the repo and serves them over MCP.

## Tools
- `list_categories` — skill categories with counts
- `list_skills` — list skills, filter by category, paginate
- `search_skills` — keyword search over names + descriptions
- `get_skill` — full SKILL.md for a skill
- `list_agents`, `list_commands`, `repo_stats`

Skills are also exposed as MCP resources: `skill://<name>`.

## Run it — stdio (Claude Code, Codex, Cursor, …)
```bash
git clone https://github.com/kurtmorales-tech/claude-skills.git
cd claude-skills
```
Add to your client's MCP config (or use `mcp/mcp.json` from this folder):
```json
{ "mcpServers": { "claude-skills": { "type": "stdio", "command": "python3", "args": ["mcp/server.py"] } } }
```

## Run it — remote (Streamable HTTP)
```bash
python3 mcp/server.py --http 3738
# POST http://localhost:3738/mcp   ·   GET /health
```
Kurt's live remote endpoint (Cloudflare Tunnel + Access, login required):
`https://mcp-skills.ravfia.online/mcp`
