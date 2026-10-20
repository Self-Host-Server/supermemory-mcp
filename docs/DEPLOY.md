# Deploying the Supermemory MCP Server

Bridges a **self-hosted** Supermemory REST API to the MCP protocol over Streamable
HTTP, gated by an Authentik OAuth login via `oauth2-proxy`. See
[`docs/superpowers/specs/2026-10-13-self-hosted-mcp-design.md`](superpowers/specs/2026-10-13-self-hosted-mcp-design.md)
for the full design.

## Prerequisites

- A running self-hosted Supermemory instance (REST API reachable, e.g. `http://192.168.1.246:6767`) with an API key.
- An Authentik instance with an OAuth2/OIDC provider + application configured for this service (redirect URI `http://<your-host>:4180/oauth2/callback`).
- Docker + Docker Compose.

## 1. Configure `.env`

```bash
cp .env.example .env
```

Fill in:

| Variable                                          | Required | Notes                                                                                                                               |
| ------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `SUPERMEMORY_API_URL`                             | yes      | Base URL of your self-hosted instance                                                                                               |
| `SUPERMEMORY_API_KEY`                             | yes      | API key from that instance                                                                                                          |
| `SUPERMEMORY_CONTAINER_TAG`                       | no       | Namespace for memories. Leave unset only if you don't need to resume a prior namespace — a new one is generated per start otherwise |
| `AUTHENTIK_HOST`                                  | yes      | e.g. `https://authentik.example.com`                                                                                                |
| `AUTHENTIK_CLIENT_ID` / `AUTHENTIK_CLIENT_SECRET` | yes      | From the Authentik OAuth2 provider you create for this app                                                                          |
| `OAUTH2_PROXY_COOKIE_SECRET`                      | yes      | `openssl rand -base64 32`                                                                                                           |
| `OAUTH2_PROXY_REDIRECT_URL`                       | no       | Defaults to `http://localhost:4180/oauth2/callback`; set to your real public URL in production                                      |
| `MCP_PUBLIC_PORT`                                 | no       | Defaults to `4180`                                                                                                                  |

In Authentik, the OIDC issuer is expected at `${AUTHENTIK_HOST}/application/o/supermemory-mcp/` — name your Authentik application slug `supermemory-mcp`, or edit `compose.yml`'s `OAUTH2_PROXY_OIDC_ISSUER_URL` to match whatever slug you used.

## 2. Run it

```bash
docker compose up -d --build
```

Two containers come up:

- `mcp-server` — internal only, no published port. Not reachable except through the proxy.
- `oauth2-proxy` — published on `${MCP_PUBLIC_PORT:-4180}`, fronts `mcp-server` with an Authentik login.

Check health:

```bash
curl http://localhost:4180/health   # should return 200, no login required
```

Hitting `/mcp` directly without logging in should redirect to Authentik (or return 401/302, never 200).

## 3. Connect an MCP client

Once logged in through the proxy (a browser session establishes the oauth2-proxy cookie), point your client at:

```
http://<your-host>:4180/mcp
```

Claude Code:

```bash
claude mcp add --transport http supermemory http://<your-host>:4180/mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "supermemory": {
      "url": "http://<your-host>:4180/mcp"
    }
  }
}
```

Tools exposed: `addToSupermemory` (`{thingToRemember}`), `searchSupermemory` (`{informationToGet}`). Prompt exposed: `Supermemory Prompt`.

## Troubleshooting

- **401/redirect loop on every request, including `/health`**: `/health` is explicitly excluded from the proxy's auth requirement (`OAUTH2_PROXY_SKIP_AUTH_ROUTES`). If it's also failing, the proxy container itself is misconfigured — check `docker compose logs oauth2-proxy`.
- **`mcp-server` never becomes healthy**: it validates required env vars (`SUPERMEMORY_API_URL`, `SUPERMEMORY_API_KEY`) at startup and exits if missing — check `docker compose logs mcp-server`.
- **Tool calls fail with errors from Supermemory itself**: the server passes backend errors straight through (no retry, no swallow) — the message in the MCP error response is the real one from your self-hosted instance.
- **Logging in works but tool calls still 401**: confirm `oauth2-proxy` is sending `X-Forwarded-User` (`OAUTH2_PROXY_SET_XAUTHREQUEST`/`OAUTH2_PROXY_PASS_BASIC_AUTH` in `compose.yml`) — `server/main.py` rejects any `/mcp` request missing that header.
- **Memories from a previous deployment don't show up**: set `SUPERMEMORY_CONTAINER_TAG` explicitly to the old tag; an unset tag generates a fresh one each start.
