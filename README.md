# VPS Proxy Delivery

A Codex skill for deploying, hardening, testing, and handing off independent VPS proxy nodes for non-technical users.

The skill focuses on practical delivery workflows:

- direct SSH intake and baseline checks
- BBR/fq network tuning
- Dockerized 3x-ui setup when a panel is needed
- VLESS Reality and Hysteria2 node presets
- optional residential SOCKS5 backend handling
- one-click subscription URL generation
- security trimming for Hy2-only deployments
- firewall, SSH, fail2ban, and exposed-port validation
- concise handoff documents for users

## Repository Layout

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   └── deployment-runbook.md
└── scripts/
    └── subscription_server.py
```

## Install

Copy this directory into your Codex skills folder:

```powershell
git clone https://github.com/EnvirCat/vps-proxy-delivery.git "$env:USERPROFILE\.codex\skills\vps-proxy-delivery"
```

Then use it in Codex:

```text
$vps-proxy-delivery
```

## Typical Use

Provide a VPS IP, SSH port, username, and an authentication method. The skill will guide or perform:

1. connection and OS checks
2. network tuning
3. proxy/panel deployment
4. subscription generation
5. validation
6. handoff documentation

## Security Notes

This repository intentionally contains no real VPS credentials, private keys, subscription links, residential proxy credentials, or production IP addresses.

When using the skill:

- never commit generated handoff documents that contain secrets
- keep each VPS independent unless you explicitly intend otherwise
- rotate ports and credentials if a subscription link leaks
- prefer exact-allowlist subscription endpoints for shared or resale nodes
- disable unused panels and compatibility services when a node should be Hy2-only

## Responsible Use

This project is a deployment and operations workflow. Use it only on servers you own or are authorized to administer, and comply with applicable laws, provider terms, and local network policies.

## License

MIT
