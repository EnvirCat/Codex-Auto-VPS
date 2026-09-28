# VPS-Wide Subscription Traffic Display

This reference adds a provider-quota usage display to existing Clash/Mihomo and Hiddify subscriptions without a management panel. It counts traffic on the VPS's public network interface and publishes the counters in `Subscription-Userinfo`; it does not impose a rate limit or stop traffic at the quota.

## Scope and accuracy

- The counter is VPS-wide. It includes inbound and outbound bytes on the selected public interface, such as proxy traffic, SSH, and subscription downloads. It is not a per-user or per-protocol meter.
- The meter sums interface RX and TX deltas. It retains state across process restarts and host reboots, polls every few seconds, and serves the latest persisted sample to subscription `GET` and `HEAD` requests without synchronously writing state for each request.
- A short outage that spans both a meter stop and a VPS reboot can lose at most the unsampled interval before shutdown. Keep the service enabled and monitor it.
- Confirm the provider's quota, reset boundary, time zone, current usage, and plan expiry before installation. Never infer an absolute reset date from a countdown unless its capture time is known.
- For a provider quota shown as `1000 GB`, use decimal bytes: `1,000,000,000,000`. A screenshot showing a combined used amount can seed the total; when no direction breakdown exists, place that baseline in one direction and disclose that only the initial upload/download split is approximate.
- An old usage screenshot is not a safe baseline. Obtain a current provider reading before enabling the meter.

## Design

The meter is a small Python standard-library service running as the existing `caddy` account. It binds only to `127.0.0.1`, reads only two exact allowlisted files under the subscription root, and persists counters under `/var/lib/vps-traffic-meter`. The installer replaces only the existing exact Clash and Hiddify Caddy `file_server` handlers with reverse proxies to this loopback service. Caddy continues to provide HTTPS, profile naming, update interval, cache policy, and the existing URLs. No firewall port, proxy listener, route, protocol credential, or subscription body changes.

The response includes:

```text
Subscription-Userinfo: upload=<RX bytes>; download=<TX bytes>; total=<quota bytes>; expire=<Unix timestamp>
```

Modern Hiddify profiles use this header for traffic and expiry display. Provide all four numeric fields; use `expire=0` only when the plan truly has no expiry. Mihomo-compatible clients also read the upload/download/total values. [Hiddify subscription metadata](https://github.com/hiddify/hiddify-app/wiki/Home/c94802ea77b9cd0aa06e29635c2d59add03224f4), [Hiddify parser issue and behavior](https://github.com/hiddify/hiddify-app/issues/2242), [Mihomo dashboard usage card](https://github.com/MetaCubeX/metacubexd).

## Preconditions

1. Audit the active Caddyfile and confirm it has exactly one matcher/handler for each of the existing `clash.yaml` and `hiddify.txt` endpoints. Both must serve from the same private subscription root, use exact paths, and have no existing `Subscription-Userinfo` header.
2. Identify the public interface from `ip route get 1.1.1.1`, then confirm its `/sys/class/net/<interface>/statistics/{rx,tx}_bytes` counters are readable.
3. Record the provider's current combined usage, monthly quota, reset day/time zone, and plan expiry. Convert the total quota and initial usage to bytes.
4. Confirm Python 3.10+, systemd, and Caddy are installed, the `caddy` user/group can read both subscription files, and the chosen loopback port is unused.
5. Save the current body hashes for both subscriptions. Do not print or log their tokenized paths or contents.

## Install

Copy `scripts/traffic_meter.py` and `scripts/install_traffic_meter.py` to the VPS over the existing SSH session. Do not place credentials or subscription URLs in either script.

Run a no-change preflight first:

```bash
python3 install_traffic_meter.py \
  --interface <public-interface> \
  --quota-bytes <confirmed-quota-bytes> \
  --reset-day <confirmed-day-of-month> \
  --timezone <provider-cycle-time-zone> \
  --initial-upload-bytes <provider-upload-bytes-or-zero> \
  --initial-download-bytes <provider-download-bytes> \
  --expire-epoch <verified-expiry-epoch-or-zero> \
  --dry-run
```

Only after the dry run passes, repeat the command without `--dry-run`. The installer validates the original and candidate Caddyfiles, creates a root-only backup of only the Caddyfile, installs a least-privilege systemd unit and root-owned configuration readable by the Caddy group, starts the loopback service, checks both exact subscription paths, and reloads Caddy. If the service or Caddy validation fails, it leaves or restores the original public handlers.

Do not configure an initial baseline twice. The first successful meter sample persists state; subsequent starts use that state. At the confirmed local reset boundary, usage returns to zero and begins accumulating the next period.

## Validation

1. `systemctl is-active vps-traffic-meter.service caddy.service` reports both active.
2. `ss -ltnp` shows the meter only on `127.0.0.1:<port>`; the firewall is unchanged.
3. Send `HEAD` and `GET` to both existing HTTPS subscriptions. Expect HTTP 200, the existing profile/title/filename headers, and `Subscription-Userinfo` containing integer `upload`, `download`, `total`, and `expire` fields.
4. Compare the post-install GET body SHA-256 with the pre-install hash for each file; the bytes must be identical.
5. Unknown paths, sibling files, and `.new` files still return 404. Confirm the service journal does not contain any subscription request path.
6. Import or refresh in the target client and verify the usage bar. Some clients refresh subscription metadata only during an update or profile open.

## Rollback

Restore the exact root-only Caddyfile backup and run `caddy validate --config /etc/caddy/Caddyfile` followed by `systemctl reload caddy.service`. Then disable the meter with `systemctl disable --now vps-traffic-meter.service`. Preserve its state directory until the user confirms the rollback is final; do not delete unrelated subscription files or credentials.

The metadata is informational only. If the user needs per-client caps or automatic cutoff at 1 TB, this design is insufficient; that requires explicit per-user accounting and enforcement, which is a separate change.
