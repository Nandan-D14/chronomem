"""`chronomem-connect`: one command to plug your local ChronoMem into ChatGPT (or any remote MCP client).

Starts the MCP server over HTTP, opens a Cloudflare quick tunnel, protects it with a secret URL path,
and prints the URL to paste into ChatGPT -> Settings -> Connectors / Plugins -> Add custom MCP server.
"""
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home() / ".chronomem"
STATUS = HOME / "connect.json"
TOKEN_FILE = HOME / "token"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _token() -> str:
    HOME.mkdir(exist_ok=True)
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    tok = secrets.token_urlsafe(18)
    TOKEN_FILE.write_text(tok)
    return tok


def _cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe"):
        if Path(p).exists():
            return p
    return None


def status() -> dict:
    """Current connection info (read by the dashboard)."""
    if not STATUS.exists():
        return {"connected": False}
    data = json.loads(STATUS.read_text())
    try:  # alive if the local MCP server still answers (os.kill(pid, 0) would kill the process on Windows)
        socket.create_connection(("127.0.0.1", int(data.get("port", 8765))), timeout=0.5).close()
    except OSError:
        return {"connected": False}
    return {"connected": True, **{k: v for k, v in data.items() if k != "pid"}}


def run():
    cf = _cloudflared()
    if not cf:
        sys.exit("cloudflared not found. Install it: winget install Cloudflare.cloudflared  (or brew install cloudflared)")

    user = os.getenv("CHRONOMEM_USER", "default")
    port = os.getenv("MCP_PORT", "8765")
    path = f"/{_token()}/mcp"
    env = {**os.environ, "CHRONOMEM_TRANSPORT": "http", "MCP_PORT": port, "MCP_PATH": path, "CHRONOMEM_USER": user}

    print(f"[chronomem] starting MCP server for memory graph mem_{user} ...")
    server = subprocess.Popen([sys.executable, "-m", "chronomem.mcp_server"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[chronomem] opening secure tunnel ...")
    tunnel = subprocess.Popen([cf, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    url = None
    deadline = time.time() + 40
    while time.time() < deadline and url is None:
        line = tunnel.stderr.readline()
        m = URL_RE.search(line or "")
        if m:
            url = m.group(0)
    if not url:
        server.terminate(); tunnel.terminate()
        sys.exit("[chronomem] tunnel did not start; check your internet connection")

    mcp_url = url + path
    STATUS.write_text(json.dumps({"pid": os.getpid(), "url": mcp_url, "user": user, "port": int(port),
                                  "started_at": int(time.time() * 1000)}))
    print("\n" + "=" * 70)
    print("  ChronoMem is reachable from ChatGPT.\n")
    print("  ChatGPT -> Settings -> Plugins/Connectors -> Add custom MCP server")
    print("    Name:            ChronoMem")
    print(f"    Server URL:      {mcp_url}")
    print("    Authentication:  None   (the URL contains a secret token - don't share it)")
    print(f"\n  Memory graph: mem_{user}   |   Ctrl+C to disconnect")
    print("=" * 70 + "\n")

    def stop(*_):
        STATUS.unlink(missing_ok=True)
        tunnel.terminate(); server.terminate()
        print("[chronomem] disconnected")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        if tunnel.poll() is not None or server.poll() is not None:
            stop()
        tunnel.stderr.readline()  # keep draining tunnel logs


if __name__ == "__main__":
    run()
