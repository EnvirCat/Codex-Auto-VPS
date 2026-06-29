# Codex-Auto-VPS Runbook

## Intake Checklist

Collect:

- VPS IP, SSH port, username, password or key path.
- OS/version and whether reboot is allowed.
- Intended audience: personal use, resale, or shared family/team use.
- Preferred clients: Hiddify, Shadowrocket, v2rayN, sing-box, Clash-compatible apps.
- Optional backend: residential SOCKS5 host, port, username, password.

Never connect VPSes to each other unless explicitly requested.

## Connection

Use direct SSH from the local machine:

```powershell
ssh -i C:/path/to/key -p 22 root@203.0.113.10
ssh -p 55514 root@203.0.113.10
```

If Windows OpenSSH is flaky with password hosts, use PuTTY `plink` from the local machine, not another VPS.

## Baseline Checks

```bash
uname -a
cat /etc/os-release
ip -br addr
free -h
df -h
ss -tulpen
curl -4s https://api.ipify.org; echo
```

## BBR/fq

Apply only when not already enabled:

```bash
cat >/etc/sysctl.d/99-bbr.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
sysctl --system
sysctl net.core.default_qdisc net.ipv4.tcp_congestion_control
```

For kernels without BBR, report that a kernel upgrade or OS reinstall is required instead of forcing it during a no-reboot task.

## Dockerized 3x-ui Pattern

Use Docker when the VPS may already have services or when the user wants minimal host pollution.

Recommended decisions:

- Random panel port: `28xxx` or another unused high port.
- Random panel path: 10-16 hex/chars.
- Username: user-friendly but not obvious, such as `admin`.
- Password: random 16+ chars.
- Subscription service port: separate high port, for example `28703`.

Generic Docker install:

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" >/etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

For CentOS/RHEL, use Docker's official repo or the distribution package if Docker upstream does not support the old release.

Example 3x-ui container shape:

```bash
docker run -d --name 3x-ui-panel --restart unless-stopped \
  --network host \
  -v /opt/3x-ui/db:/etc/x-ui \
  -v /opt/3x-ui/cert:/root/cert \
  ghcr.io/mhsanaei/3x-ui:latest
```

Configure panel settings through 3x-ui CLI or the web UI. Verify:

```bash
docker ps
ss -tulpen | grep -E '286|2096|443|31011'
```

## Node Presets

Use simple, human-readable names:

- `1 Fast All Platforms` / `1 极速全平台`: speed-first, usually Hysteria2 if UDP works.
- `2 Android Stable`: VLESS + Reality TCP fallback.
- `3 iOS Stable`: same transport, separate UUID for per-device tracking.
- `4 Windows Stable`: same transport, separate UUID.
- `5 Mac Stable`: same transport, separate UUID.
- `6 AI Residential`: only if routing through residential SOCKS5; not speed-first.

If the panel export is blank, it usually means the inbound lacks clients or the panel cannot serialize that transport. Add explicit clients and/or use the custom subscription service.

## Security Trim Pattern

Use this pattern when the user wants maximum practical safety without keeping compatibility nodes:

1. Audit current listeners:

```bash
ss -tulpen
systemctl --type=service --state=running | grep -Ei 'xray|hysteria|x-ui|sub|docker'
docker ps
```

2. Select random high UDP ports:

```bash
shuf -i 20000-60999 -n 2
```

3. Update Hysteria2 server configs:

```bash
sed -i 's/^listen:.*/listen: :NEW_PORT/' /etc/hysteria/config.yaml
systemctl restart hysteria-server.service
```

For a residential backend, update its separate config in the same way, such as `/etc/hysteria/residential.yaml`.

4. Disable unused compatibility surfaces:

```bash
systemctl disable --now xray.service 2>/dev/null || true
docker update --restart=no 3x-ui-panel 2>/dev/null || true
docker stop 3x-ui-panel 2>/dev/null || true
```

If no containers remain, disable Docker too:

```bash
if [ -z "$(docker ps -q 2>/dev/null)" ]; then
  systemctl disable --now docker.service docker.socket containerd.service 2>/dev/null || true
fi
```

5. Rebuild subscriptions so they contain only the intended Hy2 links. Prefer separate Base64 URLs:

- `Safe-Direct-Hy2-base64`
- `Safe-Residential-Hy2-base64`

If old subscription URLs or already-imported client nodes may have leaked, rotate the active Hy2 ports, auth passwords,
and obfuscation passwords before rebuilding the subscriptions. Then serve subscriptions through an exact allowlist:
only the final approved paths should return HTTP 200, and every old alias, token path, plain-text path, or compatibility
path should return 404. Delete old subscription files and backups that contain VLESS links, old ports, or old Hy2
credentials; do not leave rollback archives with retired secrets on the VPS.

6. Enable least-privilege firewall:

```bash
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow SSH_PORT/tcp
ufw allow SUB_PORT/tcp
ufw allow DIRECT_HY2_PORT/udp
ufw allow RESIDENTIAL_HY2_PORT/udp
ufw --force enable
ufw status verbose
```

For SSH hardening on key-based hosts, disable password and keyboard-interactive login, keep root login key-only if the
user still manages the machine as root, and add fail2ban for sshd:

```bash
apt-get install -y fail2ban unattended-upgrades
cat >/etc/fail2ban/jail.d/sshd-local.conf <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
backend = systemd
maxretry = 4
findtime = 10m
bantime = 6h
EOF
systemctl enable --now fail2ban

cat >/etc/ssh/sshd_config.d/99-codex-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password
X11Forwarding no
AllowTcpForwarding no
MaxAuthTries 3
LoginGraceTime 30
EOF
sshd -t && systemctl reload ssh.service
```

7. Validate:

```bash
ss -tulpen | grep -E '(:SSH_PORT|:SUB_PORT|:DIRECT_HY2_PORT|:RESIDENTIAL_HY2_PORT)'
curl -fsS http://IP:SUB_PORT/Safe-Direct-Hy2-base64
curl -fsS http://IP:SUB_PORT/Safe-Residential-Hy2-base64
```

Use a temporary Hy2 client on the server to confirm exit IP and HTTPS reachability. Do not leave the temporary client
running. Also explicitly test old subscription aliases and old random token paths; expected result is 404.

## One-Click Subscription Service

Install `scripts/subscription_server.py` on the VPS, then create:

```bash
mkdir -p /opt/vps-subscription
cat >/opt/vps-subscription/token <<'EOF'
random-private-token
EOF
cat >/opt/vps-subscription/aliases.txt <<'EOF'
US-Fast-VPS
US-Fast-VPS-base64
EOF
cat >/opt/vps-subscription/sub.txt <<'EOF'
hysteria2://...
vless://...
EOF
```

Systemd unit:

```ini
[Unit]
Description=VPS subscription server
After=network-online.target
Wants=network-online.target

[Service]
Environment=SUBSCRIPTION_DIR=/opt/vps-subscription
Environment=SUBSCRIPTION_PORT=28703
ExecStart=/usr/bin/python3 /opt/vps-subscription/server.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now vps-subscription.service
systemctl status vps-subscription.service --no-pager
```

Validate:

```powershell
Invoke-WebRequest -UseBasicParsing http://IP:28703/US-Fast-VPS
Invoke-WebRequest -UseBasicParsing http://IP:28703/US-Fast-VPS-base64
```

Hiddify often displays the URL path as the subscription name. Prefer a friendly alias path over a random token path.

## Validation Matrix

Minimum checks:

- SSH still works.
- Panel URL returns HTTP 200 or login page.
- Subscription URL returns non-empty content with the fastest link first.
- `ss -tulpen` shows expected listening ports.
- Client can connect and exit IP is expected.
- Target sites load, if testing is permitted and available.

Speed triage:

- Direct VPS speed good but client slow: likely route, client mode, UDP blocked, DNS, QUIC, or selected fallback node.
- Hysteria2 slow or unavailable: try Reality TCP fallback, then test UDP reachability.
- Residential route slow: expected; keep it for trust-sensitive use rather than downloads.
- Fast.com low but general browsing OK: check the specific CDN/streaming route before blaming the VPS.

## Handoff Document Shape

Put the most actionable items first:

```text
1. 一键订阅
普通订阅: http://IP:PORT/Friendly-Name
Base64 备用: http://IP:PORT/Friendly-Name-base64

2. 推荐选择
首选: 1 极速全平台
打不开或不稳定: 2/3/4/5 稳定节点
AI 风控: 6 AI 住宅

3. 面板
URL:
Username:
Password:

4. 注意事项
不要随意修改端口、Reality 密钥、出站、路由或 Xray 配置。
出售前请重装系统，或至少删除面板、订阅服务、SSH 密钥和日志。
```
