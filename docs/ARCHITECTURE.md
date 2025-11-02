# Architecture

- **MySQL** stores normalized searchable fields (MAC/IPv4/IPv6) plus a flexible JSON blob for nested attributes.
- **PHP API** performs CRUD, history logging, LDAP auth, and agent/poller ingestion.
- **Agents** (Linux/Python and Windows/C#) push updates on an interval (default 60s).
- **Poller** augments via SSH/WMI/WinRM (upsert by MAC/name) and can mark online/offline.
- **Sanitization rules** provide admin-managed JSON filters that pollers download to strip loopback/link-local or other sensitive data before reporting it to the API.
- **Frontend** is a lightweight SPA (no heavy framework) for speed and portability.

## Online/Heartbeat
- Agents set `online_status=online` and the server records `last_seen`.
- Poller also updates `last_seen` when probes succeed.
- A cron can mark assets offline if `last_seen` > N minutes.

## Extending
- Add more controllers and endpoints.
- Expand agents to gather software inventory, services, CVEs, etc.
- Build richer UI or replace with your preferred framework.

## Windows Polling

- The Python poller now targets Windows hosts using a tiered strategy: it prefers native WMI/DCOM (via Impacket) and automatically falls back to WinRM/PowerShell (via pywinrm) when DCOM is blocked.
- Collected datasets mirror the Unix probe: OS identity, architecture, boot time, adapter inventory (with MAC/IP details), disk usage, hardware metadata, and an optional installed applications list.
- Configure Windows credentials in `poller/config.yml`; optional keys such as `domain`, `winrm_transport`, `winrm_use_ssl`, `applications_limit`, and `collect_applications` fine-tune authentication and inventory breadth. Leaving these fields empty falls back to safe defaults (NTLM and CredSSP try 5985 first, then 5986 with TLS; Kerberos honours the same order) with 30s/20s timeouts, and setting `collect_applications: false` now skips software enumeration entirely.
- Results are merged into the standard asset payload so existing API/UX surfaces immediately benefit from richer Windows telemetry.
- For ad-hoc validation, run `python poller/manual_windows_probe.py --pretty --host <host> --username <user> --password <pass>` (optionally seeding values from `poller/config.yml`) to exercise the collector outside the main poller loop.

## Cisco Polling

- Network gear can now be polled with `poll_type = ssh_cisco`, leveraging the dedicated `poller/cisco_collectors.py` workflow.
- The collector establishes an SSH session, disables paging, optionally enters enable mode, and runs a curated set of `show` commands to capture platform details, modules, and interface status/description data.
- Interfaces are enumerated with both IPv4 and IPv6 reachability (`show ip interface brief vrf all` plus `show ipv6 interface brief`), so dual-stack addressing is preserved in the asset payload alongside per-interface status.
- VRF membership is captured from the CLI output; each interface is tagged with its VRF (where applicable) and the normalized response includes a `network.vrfs[]` summary of route distinguishers and attached interfaces.
- All collected addresses are filtered through the sanitization manager before delivery, ensuring link-local, loopback, or otherwise excluded ranges never reach the API payload.
- Sanitization now also validates that every recorded address parses as a proper IPv4 or IPv6 literal, preventing CLI prompts or malformed values from leaking into asset IP lists.
- Store the primary SSH credential in `poll_username`/`poll_password` and supply a `poll_enable_password` when the device requires `enable` to access privileged commands. Devices that grant the login account sufficient rights can leave the enable password blank.
- Results flow through the sanitization pipeline and land in the same asset schema (interfaces, IPs, MACs, chassis identity) so downstream consumers do not require special handling.
