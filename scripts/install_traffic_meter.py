#!/usr/bin/env python3
"""Install the VPS-wide traffic meter behind existing Caddy subscription routes."""

from __future__ import annotations

import argparse
import http.client
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SERVICE_NAME = "vps-traffic-meter.service"
SERVICE_SCRIPT = Path("/usr/local/lib/vps-traffic-meter/traffic_meter.py")
ENV_FILE = Path("/etc/default/vps-traffic-meter")
UNIT_FILE = Path("/etc/systemd/system") / SERVICE_NAME


class InstallError(RuntimeError):
    pass


def _visible_code(line: str) -> str:
    """Remove Caddyfile comments/quoted strings for brace counting."""
    output: list[str] = []
    quoted = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            if quoted:
                output.append(" ")
            continue
        if char == "\\" and quoted:
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            output.append(" ")
            continue
        if char == "#" and not quoted:
            break
        output.append(" " if quoted else char)
    return "".join(output)


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        visible = _visible_code(lines[index])
        depth += visible.count("{") - visible.count("}")
        opened = opened or "{" in visible
        if opened and depth == 0:
            return index + 1
    raise InstallError("Caddyfile contains an incomplete handler block")


def _find_subscription_handler(lines: list[str], kind: str, suffix: str) -> tuple[int, int, str, str]:
    marker = f"@{kind}"
    matcher_pattern = re.compile(rf"^\s*{re.escape(marker)}\s+path\s+(\S+)\s*$")
    matcher_hits = [(index, matcher_pattern.match(line)) for index, line in enumerate(lines)]
    matches = [(index, match.group(1)) for index, match in matcher_hits if match]
    if len(matches) != 1:
        raise InstallError(f"expected exactly one {kind} path matcher")
    matcher_index, path = matches[0]
    if not path.startswith("/") or not path.endswith(suffix) or "*" in path or "?" in path:
        raise InstallError(f"{kind} matcher is not one exact subscription path")

    handle_pattern = re.compile(rf"^\s*handle\s+{re.escape(marker)}\s*\{{\s*$")
    handle_hits = [index for index, line in enumerate(lines) if handle_pattern.match(line)]
    if len(handle_hits) != 1:
        raise InstallError(f"expected exactly one handle for {kind}")
    start = handle_hits[0]
    end = _block_end(lines, start)
    block = lines[start:end]
    if any("subscription-userinfo" in line.lower() for line in block):
        raise InstallError(f"{kind} handler already sets Subscription-Userinfo")
    roots = [
        match.group(1)
        for line in block
        if (match := re.match(r"^\s*root\s+\*\s+(\S+)\s*$", line.rstrip("\r\n")))
    ]
    if len(roots) != 1 or not roots[0].startswith("/"):
        raise InstallError(f"{kind} handler must have one absolute static root")
    file_servers = [index for index, line in enumerate(block) if re.match(r"^\s*file_server\s*$", line.rstrip("\r\n"))]
    if len(file_servers) != 1:
        raise InstallError(f"{kind} handler must contain one file_server")
    if any("reverse_proxy" in line for line in block):
        raise InstallError(f"{kind} handler already contains a reverse proxy; refusing to stack handlers")
    return start, end, path, roots[0]


def rewrite_caddyfile(text: str, bind: str, port: int) -> tuple[str, Path, frozenset[str]]:
    lines = text.splitlines(keepends=True)
    clash = _find_subscription_handler(lines, "clash", "/clash.yaml")
    hiddify = _find_subscription_handler(lines, "hiddify", "/hiddify.txt")
    if clash[3] != hiddify[3]:
        raise InstallError("Clash and Hiddify must share the same static root")
    if clash[2].rsplit("/", 1)[0] != hiddify[2].rsplit("/", 1)[0]:
        raise InstallError("Clash and Hiddify subscription paths must share one private directory")

    backend = f"reverse_proxy {bind}:{port}"
    for start, end, _path, _root in sorted((clash, hiddify), key=lambda item: item[0], reverse=True):
        block = lines[start:end]
        file_server_index = next(
            index
            for index, line in enumerate(block)
            if re.match(r"^\s*file_server\s*$", line.rstrip("\r\n"))
        )
        indent = re.match(r"^\s*", block[file_server_index]).group(0)
        newline = "\r\n" if block[file_server_index].endswith("\r\n") else "\n"
        block[file_server_index] = indent + backend + newline
        lines[start:end] = block

    allowed = frozenset((clash[2], hiddify[2]))
    return "".join(lines), Path(clash[3]), allowed


def _atomic_write(path: Path, content: str | bytes, mode: int, uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, mode)
        os.chown(temp_path, uid, gid)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _run(command: list[str], *, generic_error: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise InstallError(generic_error)
    return result


def _validate_caddyfile(candidate: Path) -> None:
    if not shutil.which("caddy"):
        raise InstallError("Caddy is not installed")
    _run(
        ["caddy", "validate", "--config", str(candidate), "--adapter", "caddyfile"],
        generic_error="Caddy rejected the candidate configuration; live configuration was not changed",
    )


def _validate_caddy_content(caddyfile: Path, content: str) -> None:
    original_stat = caddyfile.stat()
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{caddyfile.name}.traffic-meter-check.", dir=caddyfile.parent
    )
    candidate = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(candidate, stat.S_IMODE(original_stat.st_mode))
        os.chown(candidate, original_stat.st_uid, original_stat.st_gid)
        _validate_caddyfile(candidate)
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _check_backend(bind: str, port: int, allowed: frozenset[str]) -> None:
    for request_path in allowed:
        last_error: Exception | None = None
        for attempt in range(20):
            connection = http.client.HTTPConnection(bind, port, timeout=3)
            try:
                connection.request("HEAD", request_path)
                response = connection.getresponse()
                header = response.getheader("Subscription-Userinfo", "")
                fields = dict(
                    pair.strip().split("=", 1)
                    for pair in header.split(";")
                    if "=" in pair
                )
                if response.status != 200 or not all(
                    key in fields and fields[key].strip().isdigit()
                    for key in ("upload", "download", "total", "expire")
                ):
                    raise InstallError("traffic meter backend did not return valid subscription metadata")
                break
            except (OSError, http.client.HTTPException) as exc:
                last_error = exc
                if attempt == 19:
                    raise InstallError("traffic meter backend health check failed") from last_error
                time.sleep(0.25)
            finally:
                connection.close()


def _check_preconditions(args: argparse.Namespace) -> None:
    if not args.interface or "/" in args.interface or ".." in args.interface:
        raise InstallError("interface name is invalid")
    counter_dir = Path("/sys/class/net") / args.interface / "statistics"
    if not all((counter_dir / name).is_file() for name in ("rx_bytes", "tx_bytes")):
        raise InstallError("network interface byte counters are unavailable")
    try:
        ZoneInfo(args.timezone)
    except Exception as exc:
        raise InstallError("timezone is not available on this system") from exc
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((args.bind, args.port))
    except OSError as exc:
        raise InstallError("the loopback meter port is already in use") from exc


def _env_file(args: argparse.Namespace, root: Path, allowed: frozenset[str]) -> str:
    values = {
        "METER_BIND": args.bind,
        "METER_PORT": str(args.port),
        "METER_INTERFACE": args.interface,
        "METER_STATIC_ROOT": str(root),
        "METER_ALLOWED_PATHS": ";".join(sorted(allowed)),
        "METER_STATE_FILE": "/var/lib/vps-traffic-meter/state.json",
        "METER_QUOTA_BYTES": str(args.quota_bytes),
        "METER_INITIAL_UPLOAD_BYTES": str(args.initial_upload_bytes),
        "METER_INITIAL_DOWNLOAD_BYTES": str(args.initial_download_bytes),
        "METER_RESET_DAY": str(args.reset_day),
        "METER_TIMEZONE": args.timezone,
        "METER_EXPIRE_EPOCH": str(args.expire_epoch),
        "METER_POLL_SECONDS": str(args.poll_seconds),
    }
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise InstallError(f"invalid newline in {key}")
    return "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()) + "\n"


def _unit_file() -> str:
    return f"""[Unit]
Description=VPS-wide subscription traffic meter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=caddy
Group=caddy
EnvironmentFile={ENV_FILE}
ExecStart=/usr/bin/python3 {SERVICE_SCRIPT}
Restart=on-failure
RestartSec=3
UMask=0077
StateDirectory=vps-traffic-meter
StateDirectoryMode=0700
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=
RestrictAddressFamilies=AF_INET AF_UNIX

[Install]
WantedBy=multi-user.target
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddyfile", type=Path, default=Path("/etc/caddy/Caddyfile"))
    parser.add_argument("--interface", required=True, help="VPS public network interface")
    parser.add_argument("--quota-bytes", type=int, required=True)
    parser.add_argument("--reset-day", type=int, required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--initial-upload-bytes", type=int, default=0)
    parser.add_argument("--initial-download-bytes", type=int, default=0)
    parser.add_argument("--expire-epoch", type=int, required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19087)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def install(args: argparse.Namespace) -> None:
    if args.quota_bytes <= 0 or not 1 <= args.reset_day <= 31:
        raise InstallError("quota must be positive and reset day must be 1..31")
    if args.initial_upload_bytes < 0 or args.initial_download_bytes < 0 or args.expire_epoch < 0:
        raise InstallError("initial counters and expiration must be non-negative")
    if args.poll_seconds <= 0 or not 1 <= args.port <= 65535:
        raise InstallError("poll interval or port is invalid")
    if args.bind != "127.0.0.1":
        raise InstallError("the meter must bind to 127.0.0.1 only")
    _check_preconditions(args)

    if not args.caddyfile.is_file():
        raise InstallError("Caddyfile was not found")
    original = args.caddyfile.read_text(encoding="utf-8")
    changed, static_root, allowed = rewrite_caddyfile(original, args.bind, args.port)
    _validate_caddyfile(args.caddyfile)
    _validate_caddy_content(args.caddyfile, changed)
    if not static_root.is_dir():
        raise InstallError("subscription static root does not exist")
    for request_path in allowed:
        file_path = (static_root / request_path.lstrip("/")).resolve(strict=False)
        try:
            file_path.relative_to(static_root.resolve())
        except ValueError as exc:
            raise InstallError("subscription path escapes the static root") from exc
        if not file_path.is_file():
            raise InstallError("an allowlisted subscription file is missing")

    service_script_source = Path(__file__).with_name("traffic_meter.py")
    if not service_script_source.is_file():
        raise InstallError("traffic_meter.py must be alongside this installer")

    if args.dry_run:
        print("dry run passed: two exact subscription handlers found; no files changed")
        return
    if os.geteuid() != 0:
        raise InstallError("run the installer as root")
    import grp
    import pwd

    try:
        caddy_user = pwd.getpwnam("caddy")
        caddy_group = grp.getgrnam("caddy")
    except KeyError as exc:
        raise InstallError("the existing caddy service account was not found") from exc
    if caddy_user.pw_gid != caddy_group.gr_gid:
        raise InstallError("Caddy user and group do not match the expected service account")

    candidate_content = changed
    expected_env = _env_file(args, static_root, allowed)
    expected_unit = _unit_file()
    existing_files = [path.exists() for path in (ENV_FILE, UNIT_FILE, SERVICE_SCRIPT)]
    if any(existing_files):
        if not all(existing_files):
            raise InstallError("a partial meter installation exists; inspect it before resuming")
        if (
            ENV_FILE.read_text(encoding="utf-8") != expected_env
            or UNIT_FILE.read_text(encoding="utf-8") != expected_unit
            or SERVICE_SCRIPT.read_bytes() != service_script_source.read_bytes()
        ):
            raise InstallError("existing meter files differ from this installer; refusing to overwrite them")
        resume_partial = True
    else:
        resume_partial = False

    original_stat = args.caddyfile.stat()
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = Path("/root/codex-backups/traffic-meter")
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    backup_file = backup_dir / f"Caddyfile.{stamp}.bak"
    _atomic_write(backup_file, original, 0o600, 0, 0)

    if not resume_partial:
        _atomic_write(SERVICE_SCRIPT, service_script_source.read_bytes(), 0o644, 0, 0)
        _atomic_write(ENV_FILE, expected_env, 0o640, 0, caddy_group.gr_gid)
        _atomic_write(UNIT_FILE, expected_unit, 0o644, 0, 0)

    _run(["systemctl", "daemon-reload"], generic_error="systemd could not reload unit files")
    _run(
        ["systemctl", "enable", "--now", SERVICE_NAME],
        generic_error="traffic meter service failed to start; Caddy is unchanged",
    )
    try:
        _check_backend(args.bind, args.port, allowed)
    except InstallError:
        subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME], text=True, capture_output=True, check=False)
        raise

    temp_caddy = args.caddyfile.with_name(f".{args.caddyfile.name}.traffic-meter.tmp")
    try:
        _atomic_write(temp_caddy, candidate_content, stat.S_IMODE(original_stat.st_mode), original_stat.st_uid, original_stat.st_gid)
        os.replace(temp_caddy, args.caddyfile)
        try:
            _run(["systemctl", "reload", "caddy.service"], generic_error="Caddy reload failed")
        except InstallError:
            _atomic_write(args.caddyfile, backup_file.read_bytes(), stat.S_IMODE(original_stat.st_mode), original_stat.st_uid, original_stat.st_gid)
            subprocess.run(["systemctl", "reload", "caddy.service"], text=True, capture_output=True, check=False)
            raise
    finally:
        try:
            temp_caddy.unlink()
        except FileNotFoundError:
            pass

    print("installed: two exact subscription endpoints now include monthly traffic metadata")
    print("Caddy configuration backup stored with root-only permissions")
    print("no proxy, firewall, route, or subscription-body settings were changed")


def main() -> int:
    try:
        install(_parse_args())
    except (InstallError, OSError, ValueError) as exc:
        print(f"traffic meter installation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
