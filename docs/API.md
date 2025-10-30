# API Overview

Base: `/api.php?action=...`

## Auth
- `POST action=login` body: `{ "username": "...", "password": "..." }`
- `GET action=me`
- `POST action=logout`

## Assets
- `GET action=assets&q=<search>`
- `GET action=asset_get&id=<uuid>`
- `POST action=asset_create` body: `{ name, type, mac, owner_user_id, ips:[], attributes:{} }`
- `POST action=asset_update` body: `{ id, ...fields }`
- `DELETE action=asset_delete&id=<uuid>`

## Agents
- `POST action=agent_register` (admin) body: `{ name, platform, bind_asset }` → `{ token, downloads }`
- `POST action=agent_push` headers: `X-Agent-Token: <token>` body:
  ```json
  {
    "asset": {
      "id": "optional-uuid",
      "name": "myhost",
      "mac": "aa:bb:...",
      "type": "workstation|server|iot",
      "owner_user_id": 1,
      "ips": ["10.0.0.5","fe80::1"],
      "attributes": {
        "os": {"family":"linux","version":"..."},
        "apps": [{"name":"vim","version":"9.0"}]
      }
    },
    "online_status": true
  }
  ```
- `GET action=agent_download_linux&token=...` — token-injected Python script

## Poller
- `GET action=poller_sanitization_get`
  - Admin session: returns latest sanitization rules JSON and metadata.
  - Agent request: include `token=<agent-token>` query parameter or `X-Agent-Token` header to fetch rules; response includes a `checksum` for caching.
- `POST action=poller_sanitization_save` (admin)
  - Body: `{ "raw": "{ ...json... }" }` or `{ "rules": { ...object... } }`
  - Normalizes and persists sanitization rules used by poller agents to filter sensitive data (loopback, link-local ranges, etc.).
- Existing poller configuration endpoints remain available: `poller_config`, `poller_config_update`, `pollers_list`, `poller_settings_save`, `poller_settings_delete`, `poller_start`, `poller_stop`, `poller_logs`.

## Change Log
Part of `asset_get` response.
