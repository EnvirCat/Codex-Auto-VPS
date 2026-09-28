---
name: codex-auto-vps
description: 中文 VPS 自动部署、网络优化、安全加固与订阅交付 Skill。Use when the user provides VPS SSH/login details or asks for 3x-ui, BBR, VLESS Reality, Hysteria2, residential SOCKS5 backend, Hiddify/Shadowrocket subscriptions, speed testing, route checks, panel credentials, or a foolproof Chinese handoff document.
---

# Codex-Auto-VPS

## Operating Rules

- Treat each VPS as independent. Never chain, bridge, sync, or jump through one VPS to manage another unless the user explicitly asks.
- Work from the local machine directly to the target VPS. Keep unrelated VPS credentials and services out of the new VPS.
- Prefer practical user experience over theoretical neatness: a friendly one-click subscription, clear node names, and a short handoff document matter.
- Protect secrets in final messages. Put credentials and links only in the requested handoff file or when the user needs them.
- For a sellable VPS, include cleanup/reinstall notes so the user can transfer it without leaving SSH keys, panels, logs, or proxy configs behind.

## Standard Output

At the end, produce:

- Panel URL, username, and password.
- One-click subscription URL with a friendly path, for example `http://IP:PORT/US-Fast-VPS3`.
- Base64 subscription fallback when useful, for example `.../US-Fast-VPS3-base64`.
- Node intent list: speed-first, stable-compatible, AI/residential if configured.
- Client instructions for Hiddify on Windows/Android and Shadowrocket on iOS/macOS.
- Verification summary: service status, open ports, export/IP checks, speed/route notes, and any residual risk.
- A local `.txt` handoff document in the workspace.

For security-hardening requests, produce a trimmed handoff instead:

- One direct Hysteria2 subscription on a random high UDP port.
- One residential Hysteria2 subscription only when a residential SOCKS5 backend exists.
- No VLESS/Reality fallback unless the user explicitly asks for compatibility.
- No public 3x-ui panel exposure unless the user explicitly asks to keep the panel.
- Firewall summary with the exact allowed ports.

## Workflow

1. Intake and connect
   - Confirm IP, SSH port, user, auth method, OS, and whether reboot is allowed.
   - Save provided private keys only if needed, with restrictive permissions.
   - Test direct SSH to the target VPS.

2. Baseline hardening and speed
   - Enable BBR/fq and verify with `sysctl net.ipv4.tcp_congestion_control` and `sysctl net.core.default_qdisc`.
   - Install only needed packages. Avoid disruptive upgrades unless the user approves.
   - Record CPU/RAM/disk, public IP, and route/backhaul characteristics.

3. Panel and node setup
   - Prefer Dockerized 3x-ui when avoiding interference with existing services.
   - Use random high panel ports and random URL paths.
   - Create a speed-first option and a compatible fallback. Put speed-first first in subscriptions.
   - If using a residential SOCKS5 backend, keep it as a clearly labeled AI/residential route, not the default speed route.
   - For security-hardening mode, prefer Hysteria2-only and remove/disable compatibility nodes.

4. Subscription UX
   - Do not expose the random token as the user-facing subscription name.
   - Create a friendly alias path such as `US-Fast-VPS3`, `US-LAX-Fast`, or `US-AI-Residential`.
   - Keep the token URL as a private fallback.
   - Test plain and base64 subscription URLs from the local machine.

5. Validation
   - Check services, listening ports, firewall, and external reachability.
   - Import the subscription or test the links with a local client/proxy when possible.
   - Verify exit IP and access to the user-relevant categories: AI sites, streaming, and general web.
   - If speed is poor, distinguish server capacity from client route, UDP blocking, DNS/QUIC/browser issues, and client-selected node.

6. Handoff
   - Write a concise `.txt` file for a non-technical user.
   - Put "which one to choose" first: normally `1 Fast / speed-first`; use stable only when fast is blocked.
   - Include what not to touch in the panel.

## Security-Hardening Mode

Use this mode when the user asks to reduce exposed services, delete unused nodes, improve firewall posture, or keep only fast subscriptions.

Required actions:

- Keep SSH reachable before enabling any firewall.
- Move Hysteria2 off common UDP ports like `443` and `8444` when the user values lower scan noise over captive-network compatibility.
- Pick random high UDP ports, normally in `20000-60999`, and update the Hysteria2 configs and subscription links.
- Stop and disable Xray/VLESS services when the final target is Hy2-only.
- Stop and disable public 3x-ui Docker/panel exposure when the user no longer needs the panel.
- Enable UFW or equivalent with default-deny inbound and allow only SSH, subscription HTTP, and the active Hy2 UDP ports.
- Keep a short warning in the handoff: high UDP ports do not reduce cryptographic security risk by themselves and may fail on restrictive Wi-Fi or corporate networks.

Validation:

- Confirm old ports are closed externally when possible.
- Confirm `ss -tulpen` only shows expected listeners.
- Confirm subscriptions return 200 and contain only intended nodes.
- Confirm each Hy2 node exits through the expected IP and can reach OpenAI API or another simple HTTPS target.

## VPS-Wide Traffic Display

When the user asks to show remaining traffic without a management panel, first confirm the VPS provider's quota, reset day/time zone, and current usage. Treat the display as VPS-wide transfer accounting, not per-user or per-node accounting: sum RX and TX byte deltas on the public network interface. State clearly that this metadata reports usage but does not throttle or stop traffic at the quota.

Use decimal bytes when the provider defines a quota as `1000 GB` (`1,000,000,000,000` bytes). Seed the first meter state from a current provider usage reading so installation does not reset the displayed allowance. If the provider only supplies a combined usage value, preserve the total and explain that the initial upload/download split is approximate. Use the provider's reset cycle and server time zone; never infer a calendar day from an undated screenshot.

For an existing Caddy-hosted subscription, use `scripts/traffic_meter.py` with `scripts/install_traffic_meter.py` and read `references/traffic-metering.md` first. The installer must:

- Bind the meter only to `127.0.0.1`; do not open a firewall port or expose a panel.
- Replace only the two existing, exact Clash and Hiddify static handlers with the local meter backend. Preserve the subscription bodies, node credentials, routing, titles, update intervals, and all unrelated Caddy routes.
- Keep an exact, root-only Caddyfile backup and validate the candidate before reload.
- Serve only the two allowlisted subscription paths. Do not log request paths because subscription paths are bearer secrets.
- Persist interface counters across service restarts and VPS reboots, and reset usage only at the confirmed monthly boundary.
- Add a valid `Subscription-Userinfo` header with numeric `upload`, `download`, `total`, and `expire` fields. Use the confirmed quota in bytes and a verified expiry timestamp (or `0` when the plan has no expiry); malformed or incomplete metadata can make clients omit the usage display.

Validate both `HEAD` and `GET` on the existing HTTPS subscriptions, require status 200 and valid numeric metadata, confirm the response body remains byte-for-byte unchanged, and verify every unknown path still returns 404. Confirm the meter listens only on loopback and that no node service, protocol port, firewall rule, or subscription URL changed.

## Resources

- Read [references/deployment-runbook.md](references/deployment-runbook.md) before live deployment or troubleshooting.
- Read [references/traffic-metering.md](references/traffic-metering.md) before adding provider-quota usage metadata to a subscription.
- Use [scripts/subscription_server.py](scripts/subscription_server.py) as the reusable HTTP subscription server template when a client-friendly one-click subscription is needed.
- Use [scripts/traffic_meter.py](scripts/traffic_meter.py) and [scripts/install_traffic_meter.py](scripts/install_traffic_meter.py) for an allowlisted, loopback-only VPS-wide usage meter.
