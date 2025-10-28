# Asset Tracker (PHP + MySQL + JS + Python + C#)

A starter, production-minded **Device/Asset Tracking System** to maintain a real-time system-of-record for enterprise assets (computers, servers, IoT, etc.).

- Frontend: vanilla HTML/CSS/JS (single-page app) + fetch() to a PHP API
- Backend: PHP (no framework), MySQL (JSON columns for nested properties), LDAP (Active Directory) login
- Agents: 
  - **Linux agent (Python)** — lightweight daemon using a token to push updates
  - **Windows agent (C# .NET)** — Windows Service posting updates
- Poller: **Python** polling engine (SSH for Linux; optional WMI/PowerShell for Windows) to complement push agents
- Auth:
  - Frontend: LDAP (Active Directory) via PHP LDAP funcs (placeholders, configurable)
  - Agents & Poller: Token-based (per-agent tokens; API keys for poller)
- Features:
  - UUID-based Asset IDs (stable/high-entropy)
  - Multiple IPv4/IPv6 per asset
  - Nested/complex attributes via MySQL JSON
  - Full CRUD (assets, attributes, IPs)
  - Source-of-truth attribution for every update (manual/api/agent/poller)
  - Asset history (change log) & timeline
  - Online/heartbeat tracking (agent pushes + poller probes)
  - Owner mapping from directory users

> This is a complete, extensible scaffold to accelerate integration into your environment (NGINX/Apache + PHP 8.1+, MySQL 8.0+ recommended).

## Quick Start

1. Create database & user, then load schema:
   ```bash
   mysql -u root -p < sql/schema.sql
   ```

2. Configure PHP:
   - Copy `server/config/config.sample.php` → `server/config/config.php`
   - Fill in MySQL, LDAP, site URL, and secret/token salts.

3. Serve the app (dev):
   - Point your web server docroot to `server/public/`
   - Or run PHP built-in server:
     ```bash
     php -S 0.0.0.0:8080 -t server/public
     ```

4. Visit `http://localhost:8080/` to use the UI.
   - Login with AD (LDAP) or fallback local admin (see config).

5. Agents
   - Create an agent token in UI (Settings → Agents) or via API.
   - Download per-token agent bundle (Linux/Windows) from generated URL.
   - Start the service; confirm heartbeats & updates appear under the asset.

6. Poller
   - Configure `poller/config.yml` (targets, creds).
   - Install deps: `pip install -r poller/requirements.txt`
   - Run: `python poller/poller.py`

## Directory Layout
```
server/
  public/           # Web root (index + API router + static assets)
  src/              # PHP source (controllers, db, auth)
  config/           # config.php (copy from sample)
frontend/           # SPA (built as static assets copied into public/assets)
sql/                # MySQL schema
agents/
  linux/            # Python agent + systemd unit
  windows/          # C# Windows Service agent (.NET)
poller/             # Python polling engine (SSH, optional WMI)
docs/               # API & architecture docs
scripts/            # Seeds and helper scripts
```

## Security Notes
- Store `config.php` **outside** webroot or protect tightly.
- Use HTTPS.
- Rotate API keys and agent tokens.
- Limit agent token scope by asset or group.
- Review CORS rules if exposing API across domains.

## License
MIT
