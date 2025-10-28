# Windows Agent (C#)

A minimal Windows Service that periodically gathers basic host info and POSTs to your server's `agent_push` endpoint using the provided token.

## Build
- Requires .NET (>=4.7.2 or .NET 6 if you prefer) — sample here is classic .NET Framework style.
- Edit `App.config` to set `ApiUrl` and `AgentToken`.
- Install service with: `sc create AssetAgent binPath= "C:\Path\To\AssetAgent.exe"`
- Start with: `sc start AssetAgent`
