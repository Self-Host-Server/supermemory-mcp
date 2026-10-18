# Self-Hosted Supermemory REST API Contract

**Date:** 2026-10-18  
**Probed instance:** http://192.168.1.246:6767  
**SDK:** Supermemory self-hosted, discovered at /v4 endpoint family

---

## POST /v4/memories — Add Memories

**Success (201 Created):**

Request:
```json
{
  "memories": [
    {"content": "probe: remember the blue folder"}
  ],
  "containerTag": "probe_test"
}
```

Response:
```json
{
  "documentId": "jG6XA2dDuVnDdSCPixaBj3",
  "memories": [
    {
      "id": "Gp2ctZJeZCNuASGN3vP9oa",
      "memory": "probe: remember the blue folder",
      "isStatic": false,
      "createdAt": "2026-10-18T03:36:23.954Z",
      "forgetAfter": null,
      "forgetReason": null,
      "metadata": null
    }
  ]
}
```

**Auth Failure (401 Unauthorized):**
- Status: 401
- Body: `{"error": "Unauthorized"}`
- Triggered by: missing Authorization header or invalid bearer token

**Notes:**
- `memories` is **required array** (not a scalar `content` field)
- `containerTag` is **required string**
- Response contains full memory objects; use `memories[0].id` as the stored memory ID if needed

---

## POST /v4/search — Search Memories

**Success with matches (200 OK):**

Request:
```json
{
  "q": "blue folder",
  "containerTag": "probe_test"
}
```

Response:
```json
{
  "results": [
    {
      "id": "Gp2ctZJeZCNuASGN3vP9oa",
      "memory": "probe: remember the blue folder",
      "rootMemoryId": "Gp2ctZJeZCNuASGN3vP9oa",
      "metadata": null,
      "updatedAt": "2026-10-18T03:36:23.954Z",
      "version": 1,
      "similarity": 0.8517188187315896,
      "filepath": null
    }
  ],
  "timing": 64,
  "total": 1
}
```

**Success with no matches (200 OK):**

Request:
```json
{
  "q": "zzz_no_such_memory_zzz",
  "containerTag": "probe_test"
}
```

Response:
```json
{
  "results": [],
  "timing": 106,
  "total": 0
}
```

**Auth Failure (401 Unauthorized):**
- Status: 401
- Body: `{"error": "Unauthorized"}`
- Triggered by: missing Authorization header or invalid bearer token

**Container Tag Behavior:**
- `containerTag` is **optional** in request
- When omitted, search returns results from **all** container tags (global search)
- When provided, search returns results only from that container tag

**Notes:**
- `q` is **required string** (query text)
- Empty results return `{"results": [], "timing": N, "total": 0}` — never null or absent
- Each result in `results` array includes a `memory` field (the stored text) and metadata

---

## Request Headers (Both Endpoints)

**Required:**
- `Authorization: Bearer <SUPERMEMORY_API_KEY>` — the API key from self-hosted instance setup
- `Content-Type: application/json`

**Response Headers (Both):**
- `Content-Type: application/json`
- `Vary: Origin`
- `Server-Timing: total;dur=<ms>;desc="Total Response Time"`

---

## Status Codes and Error Handling

| Status | Scenario | Body |
|--------|----------|------|
| 201 | `/v4/memories` success | `{"documentId": "...", "memories": [...]}` |
| 200 | `/v4/search` success (any result count) | `{"results": [...], "timing": N, "total": N}` |
| 401 | Auth failure (any endpoint) | `{"error": "Unauthorized"}` |
| 400 | Bad request (malformed JSON, missing required fields) | Error details (varies) |
| 404 | Route not found | Plain text: `404 Not Found` |

---

## Task 2 Implementation Notes

**Client library (`server/client.py`) must:**
1. POST to `/v4/memories` with `memories` array (singular content wrapped in array)
2. POST to `/v4/search` with `q` and optional `containerTag`
3. Parse response `results` array; return empty-result message if `total == 0`
4. Pass through 401 errors; log request but **never log the Authorization header or API key**
5. Handle timeouts (backend latency observed: 20-111ms; set timeout ~15-30s for network margin)
6. For add-memory success, extract and store the returned memory ID if tracking is needed

---

## Supermemory Instance Details

- **Host:** 192.168.1.246
- **Port:** 6767
- **Protocol:** HTTP (no HTTPS in local self-hosted setup)
- **API base path:** `/v4/`
- **Auth method:** Bearer token (API key from self-hosted admin panel)

