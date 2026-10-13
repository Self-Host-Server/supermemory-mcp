# Self-Hosted Supermemory MCP Server — Design

**Date:** 2026-10-13  
**Author:** Claude Code (brainstorming)  
**Status:** Design review in progress

---

## Intent & Why

The official Supermemory MCP server (`mcp.supermemory.ai`) runs on Cloudflare Workers and requires the hosted Supermemory API. Users who self-host the core Supermemory server (via Docker to `localhost:6767` or similar) have no way to access their memories via MCP protocol — the official MCP endpoint is cloud-only.

This repo provides a reusable, self-hostable MCP server that bridges any self-hosted Supermemory REST API to the MCP protocol, so users can:

- Run their own Supermemory instance (REST API, no MCP)
- Deploy this MCP server as a Docker container on the same network
- Connect Claude (or any MCP client) to the MCP server via SSE over HTTP
- Use all MCP memory tools against their own self-hosted data

The repo is a public template: users fork/clone it, set env vars pointing to their own self-hosted Supermemory instance and auth, and deploy via `docker compose up`.

---

## Goals

1. **Expose MCP tools** that match the official Supermemory MCP interface:
   - `addToSupermemory` (input: `{thingToRemember: string}`) → calls `/v4/memories/add`
   - `searchSupermemory` (input: `{informationToGet: string}`) → calls `/v4/search`
   - Expose a static MCP prompt: `Supermemory Prompt` (primes the model to proactively use memory)

2. **Use self-hosted instance credentials** via environment variables:
   - `SUPERMEMORY_API_URL` (e.g., `http://192.168.1.246:6767`) — required
   - `SUPERMEMORY_API_KEY` (e.g., `sm_...`) — required, from self-hosted instance's API key retrieval
   - `SUPERMEMORY_CONTAINER_TAG` (optional, defaults to a generated user ID or explicit value) — namespace for memories

3. **Run as always-on Docker service**, reachable over HTTP/SSE:
   - MCP server container + Authentik OAuth proxy container
   - Listens on a configurable port (default: `5555`)
   - Exposes `GET /sse` for SSE stream, `POST /messages` for MCP messages
   - Protected by Authentik OAuth — unauthorized requests are redirected to login
   - Can run on the same network as the self-hosted Supermemory instance

4. **Be a public, reusable template** so anyone can self-host their own instance:
   - Clear `.env.example` with all required/optional vars
   - Minimal, readable source code
   - `compose.yml` ready to deploy
   - Docs for configuration and MCP client setup (`.mcp.json`, Claude Desktop config)

---

## Non-Goals

- **Not a replacement for the official MCP server.** We don't modify, proxy, or cache the hosted Supermemory API. We only bridge self-hosted instances.
- **Not adding storage or state beyond what Supermemory provides.** No local embedding cache, no additional vector DB, no session management beyond passing through the user's container tag.
- **Not modifying the Supermemory REST API contract.** We call it as-is; if Supermemory changes its API, this server changes in lockstep.

---

## Anti-Goals

- **Must not lose memories in transit.** Errors from the backend Supermemory instance are passed through to the client; we don't silently fail or drop requests.
- **Must not expose the API key in logs, error messages, or responses.** All logging sanitizes auth headers and bearer tokens.
- **Must not add a single point of failure between the MCP client and self-hosted Supermemory.** This server is a thin shim; it does not cache, transform, or delay requests.

---

## Constraints

1. **Self-hosted Supermemory API is the source of truth.** We depend entirely on its REST endpoints. If the self-hosted instance is down, the MCP server fails gracefully.
2. **Single-user per deployment.** Each `docker compose up` instance uses one API key pointing to one user's Supermemory container tag. Multi-tenant SaaS is out of scope.
3. **Authentik OAuth required.** The MCP server is protected by Authentik OAuth proxy. Unauthorized requests are rejected before reaching the MCP endpoints.
4. **No fancy transport beyond SSE.** We expose SSE for network clients; stdio is not supported (users who want stdio would use this server's SSE endpoint from their local machine or wrap it differently).
5. **Python runtime, FastAPI + mcp SDK.** Chosen for simplicity and to reuse existing template infrastructure (ruff, tox, pyproject.toml).
6. **Docker-only distribution.** No pip package, no npm package. Users clone the repo, configure `.env`, and deploy via Docker Compose.

---

## How It Gets Made (Decisions User Made)

1. **Deployment model:** Always-on Docker container (user decided)
2. **Transport:** SSE over HTTP for network reachability (follows from "always-on" + not localhost)
3. **Language:** Python (user chose)
4. **Hosting:** Docker Compose on the same network as self-hosted Supermemory (implied by user's setup)
5. **Scope of tools:** Mirror the official two (`addToSupermemory`, `searchSupermemory`) + one prompt (matches official behavior)
6. **Authentication:** Authentik OAuth proxy protecting the MCP server (user decided)

---

## How It Gets Made (Builder Discretion)

1. **Framework choice (FastAPI):** FastAPI provides simple HTTP + SSE support; the `mcp` Python package's `SSEServerTransport` integrates naturally. No async/await overload.
2. **Authentik integration approach:** Use Authentik's forward auth (Traefik/Nginx pattern) or OAuth2 Proxy container. The MCP server trusts `X-Forwarded-User` / `X-Auth-Request-User` headers from the proxy. Compose stack: `authentik-proxy` + `mcp-server`, proxy handles OAuth flow and forwards authenticated requests.
3. **Error handling:** Pass backend errors through to the MCP client; don't swallow or retry silently.
4. **Logging:** Use Python `logging` module, sanitize auth headers, log endpoint calls and latency.
5. **Dockerfile:** Single stage is fine (Python slim base, pip install from requirements.txt, run the FastAPI app). Keep it small but readable.
6. **Configuration:** Load from `.env` (or environment variables directly); `.env.example` documents all keys. Use `pydantic.BaseSettings` or simple `os.getenv()` with validation. Add Authentik OAuth vars (`AUTHENTIK_HOST`, `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_CLIENT_SECRET`).
7. **Container tag / user ID:** Default to a generated `nanoid()` or allow override via `SUPERMEMORY_CONTAINER_TAG` env var so users who already have a Supermemory instance with memories can point to their existing container tag.
8. **Healthcheck:** Include `GET /health` endpoint returning `{"ok": true}` so Docker can monitor liveness.

---

## What's Left to the Builder

1. **Source structure:** Where does `main.py` (or the entry point) live? Probably `server/` or `src/`. Keeping it simple: root-level `app.py` or `server.py` + `mcp_server.py` for the MCP logic, unless the builder wants organization.
2. **Unit tests:** Do we write tests? Likely minimal tests (mock Supermemory responses, verify tools call the right endpoints). Scope: integration tests that check the MCP tools work end-to-end with mock responses.
3. **Documentation:** README should include:
   - How to set up `.env` and deploy via `docker compose up`
   - How to configure Claude Desktop / Claude Code to connect to the SSE endpoint
   - Example `.mcp.json` or equivalent
   - Troubleshooting (connectivity, auth failures, latency)
4. **Deployment examples:** Include a `docs/` folder with example `.env` values, `.mcp.json` snippets, and optional `compose.override.yml` for local development.
5. **Versioning:** Semver based on the template's Conventional Commits + git-cliff (already configured).

---

## Open Questions for the User (None; Brainstorming Is Complete)

All decisions have been made or flagged as builder discretion. Ready for design review.

---

## Success Criteria

After this server is built and deployed:

- ✅ A user clones the repo, sets `SUPERMEMORY_API_URL`, `SUPERMEMORY_API_KEY`, and Authentik OAuth vars in `.env`
- ✅ They run `docker compose up`, the server starts with Authentik OAuth proxy protecting it
- ✅ Unauthenticated requests to the MCP endpoint are rejected or redirected to Authentik login
- ✅ After authenticating, they configure Claude Desktop / Claude Code with the SSE endpoint
- ✅ They can call `addToSupermemory` and `searchSupermemory` from Claude
- ✅ The server forwards calls to their self-hosted Supermemory REST API
- ✅ Memories are read/written to their own Supermemory instance, not the cloud
- ✅ The repo is public and reusable (no hardcoded IPs, API keys, or user-specific logic)

---

## Appendix: Official MCP Tools Reference

For comparison, the official `mcp.supermemory.ai` exposes:

```
Tool: addToSupermemory
  Input: { thingToRemember: string }
  Behavior: POST /add with user's container tag, returns memory ID or status

Tool: searchSupermemory
  Input: { informationToGet: string }
  Behavior: POST /search with user's container tag, returns concatenated chunk content

Prompt: Supermemory Prompt
  Content: Aggressive system instruction to proactively search/store memories
```

This server mirrors the tool signatures exactly; the only difference is the backend URL and auth.
