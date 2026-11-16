import json
import logging
import os
import signal
import subprocess
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

_log_dir = Path(__file__).parent / "logs"
_log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[RotatingFileHandler(_log_dir / "playwright_launcher.log", maxBytes=5_000_000, backupCount=1)],
)

from fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_EXPECTED_IP = os.getenv("PROXY_EXIT_IP", "")
_SOCKS_PORT = os.getenv("PROXY_SOCKS5_PORT", "1080")
_XBROWSER = os.getenv("XBROWSER_PATH", "/home/ubuntu/bin/xbrowser")
_LOG = os.getenv("XBROWSER_LOG", "/tmp/xb.log")
_DISPLAY = os.getenv("XBROWSER_DISPLAY", ":99")
_CDP_PORT = int(os.getenv("XBROWSER_CDP_PORT", "9222"))
_PROFILE_PATTERN = os.getenv("XBROWSER_PROFILE_PATTERN", "[c]hromium.*xprofile")

mcp = FastMCP(
    "PlaywrightLauncher",
    instructions="""IMPORTANT: Always discover a tool's schema with ToolSearch BEFORE calling it for the first time.

This server opens and closes the residential-proxy Chromium that the Playwright MCP connects to over CDP at 127.0.0.1:9222.

Order of use:
1. Call playwright_open BEFORE any Playwright browser tool. It launches the browser if it is down and REFUSES if the proxy exit IP is wrong.
2. Use the Playwright MCP tools to read pages.
3. Call playwright_close when finished. It sends SIGTERM so the session cookies are written.

If playwright_open returns ok=false, STOP. Do not use the Playwright tools. The traffic would leave through the wrong IP.
""",
)


def _pids() -> list[int]:
    p = subprocess.run(["pgrep", "-f", _PROFILE_PATTERN], capture_output=True, text=True)
    return [int(x) for x in p.stdout.split()] if p.returncode == 0 else []


def _cdp_up() -> bool:
    p = subprocess.run(
        ["curl", "-s", "--max-time", "3", f"http://127.0.0.1:{_CDP_PORT}/json/version"],
        capture_output=True, text=True,
    )
    return p.returncode == 0 and '"Browser"' in p.stdout


def _exit_ip() -> str | None:
    p = subprocess.run(
        ["curl", "-s", "--max-time", "20", "-x", f"socks5h://127.0.0.1:{_SOCKS_PORT}",
         "https://ipinfo.io/json"],
        capture_output=True, text=True,
    )
    if p.returncode != 0 or not p.stdout.strip():
        return None
    try:
        return json.loads(p.stdout).get("ip")
    except json.JSONDecodeError:
        return None


def _launch() -> None:
    env = {**os.environ, "DISPLAY": _DISPLAY}
    with open(_LOG, "ab") as log:
        subprocess.Popen(
            [_XBROWSER],
            env=env, stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )


def _wait_cdp(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _cdp_up():
            return True
        time.sleep(0.5)
    return False


def _terminate() -> None:
    subprocess.run(["pkill", "-TERM", "-f", _PROFILE_PATTERN])


def _wait_gone(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pids():
            return True
        time.sleep(0.5)
    return False


@mcp.tool
def playwright_status() -> str:
    ip = _exit_ip()
    return json.dumps({
        "running": bool(_pids()),
        "cdp_port_up": _cdp_up(),
        "exit_ip": ip,
        "expected_ip": _EXPECTED_IP,
        "exit_ip_ok": ip == _EXPECTED_IP,
    }, indent=2)


@mcp.tool
def playwright_open() -> str:
    already = bool(_pids())
    if not already:
        _launch()
        if not _wait_cdp(20):
            _terminate()
            return json.dumps({"ok": False, "error": "cdp_port_never_opened"}, indent=2)
    elif not _cdp_up():
        return json.dumps({"ok": False, "error": "browser_running_without_cdp_port"}, indent=2)

    ip = _exit_ip()
    if ip != _EXPECTED_IP:
        if not already:
            _terminate()
        return json.dumps({
            "ok": False,
            "error": "wrong_exit_ip",
            "exit_ip": ip,
            "expected_ip": _EXPECTED_IP,
        }, indent=2)

    return json.dumps({
        "ok": True,
        "started": not already,
        "already_running": already,
        "cdp_endpoint": f"http://127.0.0.1:{_CDP_PORT}",
        "exit_ip": ip,
    }, indent=2)


@mcp.tool
def playwright_close() -> str:
    if not _pids():
        return json.dumps({"ok": True, "state": "already_closed"}, indent=2)
    _terminate()
    if _wait_gone(10):
        return json.dumps({"ok": True, "state": "closed"}, indent=2)
    return json.dumps({
        "ok": False,
        "state": "still_running",
        "note": "SIGTERM sent, did not exit; not using kill -9",
        "pids": _pids(),
    }, indent=2)
