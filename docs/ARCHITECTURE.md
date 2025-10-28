# Architecture

- **MySQL** stores normalized searchable fields (MAC/IPv4/IPv6) plus a flexible JSON blob for nested attributes.
- **PHP API** performs CRUD, history logging, LDAP auth, and agent/poller ingestion.
- **Agents** (Linux/Python and Windows/C#) push updates on an interval (default 60s).
- **Poller** augments via SSH/WMI (upsert by MAC/name) and can mark online/offline.
- **Frontend** is a lightweight SPA (no heavy framework) for speed and portability.

## Online/Heartbeat
- Agents set `online_status=online` and the server records `last_seen`.
- Poller also updates `last_seen` when probes succeed.
- A cron can mark assets offline if `last_seen` > N minutes.

## Extending
- Add more controllers and endpoints.
- Expand agents to gather software inventory, services, CVEs, etc.
- Build richer UI or replace with your preferred framework.
