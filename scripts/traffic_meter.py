#!/usr/bin/env python3
"""Serve allowlisted subscriptions with live VPS-wide traffic metadata."""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, time as day_time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


def _required_int(env_name: str, *, minimum: int = 0) -> int:
    raw = os.environ.get(env_name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{env_name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Config:
    bind: str
    port: int
    interface: str
    static_root: Path
    allowed_paths: frozenset[str]
    state_file: Path
    quota_bytes: int
    initial_upload_bytes: int
    initial_download_bytes: int
    reset_day: int
    timezone: ZoneInfo
    expire_epoch: int
    poll_seconds: float

    @classmethod
    def from_env(cls) -> "Config":
        allowed = frozenset(
            entry.strip()
            for entry in os.environ.get("METER_ALLOWED_PATHS", "").split(";")
            if entry.strip()
        )
        if not allowed or any(not entry.startswith("/") for entry in allowed):
            raise ValueError("METER_ALLOWED_PATHS must contain exact absolute URL paths")
        if any(".." in Path(entry).parts for entry in allowed):
            raise ValueError("METER_ALLOWED_PATHS cannot contain parent traversal")

        reset_day = _required_int("METER_RESET_DAY", minimum=1)
        if reset_day > 31:
            raise ValueError("METER_RESET_DAY must be between 1 and 31")

        poll_raw = os.environ.get("METER_POLL_SECONDS", "5")
        try:
            poll_seconds = float(poll_raw)
        except ValueError as exc:
            raise ValueError("METER_POLL_SECONDS must be a positive number") from exc
        if poll_seconds <= 0:
            raise ValueError("METER_POLL_SECONDS must be a positive number")

        return cls(
            bind=os.environ.get("METER_BIND", "127.0.0.1"),
            port=_required_int("METER_PORT", minimum=1),
            interface=os.environ.get("METER_INTERFACE", "").strip(),
            static_root=Path(os.environ.get("METER_STATIC_ROOT", "")),
            allowed_paths=allowed,
            state_file=Path(os.environ.get("METER_STATE_FILE", "")),
            quota_bytes=_required_int("METER_QUOTA_BYTES", minimum=1),
            initial_upload_bytes=_required_int("METER_INITIAL_UPLOAD_BYTES"),
            initial_download_bytes=_required_int("METER_INITIAL_DOWNLOAD_BYTES"),
            reset_day=reset_day,
            timezone=ZoneInfo(os.environ.get("METER_TIMEZONE", "UTC")),
            expire_epoch=_required_int("METER_EXPIRE_EPOCH"),
            poll_seconds=poll_seconds,
        )


def billing_cycle_start(now: datetime, reset_day: int) -> datetime:
    """Return the most recent monthly reset instant in ``now``'s timezone."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    month_start = date(now.year, now.month, 1)
    # ``reset_day`` may exceed the length of the current month.
    import calendar

    candidate_day = min(reset_day, calendar.monthrange(now.year, now.month)[1])
    candidate_date = date(now.year, now.month, candidate_day)
    if now.date() < candidate_date:
        if month_start.month == 1:
            previous_year, previous_month = month_start.year - 1, 12
        else:
            previous_year, previous_month = month_start.year, month_start.month - 1
        previous_day = min(reset_day, calendar.monthrange(previous_year, previous_month)[1])
        candidate_date = date(previous_year, previous_month, previous_day)
    return datetime.combine(candidate_date, day_time.min, tzinfo=now.tzinfo)


def _read_interface_counters(interface: str) -> tuple[int, int]:
    base = Path("/sys/class/net") / interface / "statistics"
    try:
        rx = int((base / "rx_bytes").read_text(encoding="ascii").strip())
        tx = int((base / "tx_bytes").read_text(encoding="ascii").strip())
    except (OSError, ValueError) as exc:
        raise RuntimeError("cannot read network interface byte counters") from exc
    return rx, tx


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        return "unknown"


class UsageMeter:
    def __init__(
        self,
        config: Config,
        *,
        counter_reader: Callable[[str], tuple[int, int]] = _read_interface_counters,
        boot_id_reader: Callable[[], str] = _boot_id,
    ) -> None:
        self.config = config
        self.counter_reader = counter_reader
        self.boot_id_reader = boot_id_reader
        self._lock = threading.RLock()
        self._state: dict[str, int | str] | None = None

    def _load_state(self) -> dict[str, int | str] | None:
        if not self.config.state_file.exists():
            return None
        try:
            loaded = json.loads(self.config.state_file.read_text(encoding="utf-8"))
            state: dict[str, int | str] = {
                "cycle_start": str(loaded["cycle_start"]),
                "upload": int(loaded["upload"]),
                "download": int(loaded["download"]),
                "last_rx": int(loaded["last_rx"]),
                "last_tx": int(loaded["last_tx"]),
                "boot_id": str(loaded["boot_id"]),
            }
            if any(int(state[key]) < 0 for key in ("upload", "download", "last_rx", "last_tx")):
                raise ValueError("negative counter in state")
            return state
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("traffic meter state is invalid; refusing to reset counters") from exc

    def _save_state(self, state: dict[str, int | str]) -> None:
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.config.state_file.with_name(self.config.state_file.name + ".tmp")
        payload = json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            descriptor = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_file, self.config.state_file)
            os.chmod(self.config.state_file, 0o600)
        finally:
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass

    def sample(self, now: datetime | None = None) -> dict[str, int]:
        current_time = now or datetime.now(self.config.timezone)
        if current_time.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        cycle = billing_cycle_start(current_time, self.config.reset_day).isoformat()
        rx, tx = self.counter_reader(self.config.interface)
        boot = self.boot_id_reader()

        with self._lock:
            state = self._state or self._load_state()
            if state is None:
                state = {
                    "cycle_start": cycle,
                    "upload": self.config.initial_upload_bytes,
                    "download": self.config.initial_download_bytes,
                    "last_rx": rx,
                    "last_tx": tx,
                    "boot_id": boot,
                }
            elif state["cycle_start"] != cycle:
                state = {
                    "cycle_start": cycle,
                    "upload": 0,
                    "download": 0,
                    "last_rx": rx,
                    "last_tx": tx,
                    "boot_id": boot,
                }
            else:
                rebooted = state["boot_id"] != boot
                old_rx, old_tx = int(state["last_rx"]), int(state["last_tx"])
                rx_delta = rx if rebooted or rx < old_rx else rx - old_rx
                tx_delta = tx if rebooted or tx < old_tx else tx - old_tx
                state = {
                    "cycle_start": cycle,
                    "upload": int(state["upload"]) + rx_delta,
                    "download": int(state["download"]) + tx_delta,
                    "last_rx": rx,
                    "last_tx": tx,
                    "boot_id": boot,
                }

            self._save_state(state)
            self._state = state
            return {
                "upload": int(state["upload"]),
                "download": int(state["download"]),
                "total": self.config.quota_bytes,
                "expire": self.config.expire_epoch,
            }

    def snapshot(self) -> dict[str, int]:
        """Return the latest poll without causing disk writes on subscription requests."""
        with self._lock:
            if self._state is None:
                raise RuntimeError("traffic meter has not sampled counters yet")
            return {
                "upload": int(self._state["upload"]),
                "download": int(self._state["download"]),
                "total": self.config.quota_bytes,
                "expire": self.config.expire_epoch,
            }


class SubscriptionHandler(BaseHTTPRequestHandler):
    server_version = "VpsTrafficMeter/1.0"
    sys_version = ""

    def log_message(self, _format: str, *_args: object) -> None:
        # Subscription paths are bearer secrets; never include request lines in logs.
        return

    def log_error(self, _format: str, *_args: object) -> None:
        return

    def do_HEAD(self) -> None:
        self._serve_subscription(include_body=False)

    def do_GET(self) -> None:
        self._serve_subscription(include_body=True)

    def _respond(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _serve_subscription(self, *, include_body: bool) -> None:
        app_server = self.server
        config: Config = app_server.config  # type: ignore[attr-defined]
        meter: UsageMeter = app_server.meter  # type: ignore[attr-defined]
        request_path = urlsplit(self.path).path
        if request_path not in config.allowed_paths:
            self._respond(404)
            return

        root = config.static_root.resolve()
        try:
            file_path = (root / request_path.lstrip("/")).resolve(strict=True)
            file_path.relative_to(root)
            if not file_path.is_file() or file_path.stat().st_size > 2_000_000:
                self._respond(404)
                return
            body = file_path.read_bytes() if include_body else b""
            size = file_path.stat().st_size
            usage = meter.snapshot()
        except (OSError, RuntimeError, ValueError):
            self._respond(503)
            return

        content_type = "application/x-yaml" if file_path.suffix == ".yaml" else "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Last-Modified", formatdate(file_path.stat().st_mtime, usegmt=True))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Subscription-Userinfo",
            "upload={upload}; download={download}; total={total}; expire={expire}".format(**usage),
        )
        self.end_headers()
        if include_body:
            self.wfile.write(body)


class MeterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: Config, meter: UsageMeter) -> None:
        super().__init__(address, SubscriptionHandler)
        self.config = config
        self.meter = meter


def _poll_meter(meter: UsageMeter, interval: float, stop: threading.Event) -> None:
    while not stop.wait(interval):
        try:
            meter.sample()
        except Exception as exc:  # Do not log paths or subscription data.
            print(f"traffic counter sampling failed: {type(exc).__name__}", file=sys.stderr, flush=True)


def main() -> int:
    try:
        config = Config.from_env()
        if not config.interface or not config.static_root.is_absolute() or not config.state_file.is_absolute():
            raise ValueError("interface, static root, and state file must be configured")
        meter = UsageMeter(config)
        meter.sample()
        server = MeterHTTPServer((config.bind, config.port), config, meter)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"traffic meter startup failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1

    stop = threading.Event()
    poller = threading.Thread(
        target=_poll_meter,
        args=(meter, config.poll_seconds, stop),
        name="traffic-counter-poller",
        daemon=True,
    )
    poller.start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
