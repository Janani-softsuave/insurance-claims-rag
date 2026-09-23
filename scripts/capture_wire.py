from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.core.config import ROOT_DIR

WIRE_PATH = ROOT_DIR / "analysis" / "week9" / "wire.json"


def _send(proc: subprocess.Popen, message: dict) -> None:
    line = json.dumps(message) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    proc.stdin.flush()


def _recv(proc: subprocess.Popen) -> dict:
    line = proc.stdout.readline().decode("utf-8")
    return json.loads(line)


def main() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp_servers.claims_system_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT_DIR),
    )

    exchange: list[dict] = []

    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "wire-capture-client", "version": "1.0.0"},
        },
    }
    _send(proc, initialize_request)
    initialize_response = _recv(proc)
    exchange.append({"direction": "client_to_server", "message": initialize_request})
    exchange.append({"direction": "server_to_client", "message": initialize_response})

    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    _send(proc, initialized_notification)
    exchange.append({"direction": "client_to_server", "message": initialized_notification})

    tools_list_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    _send(proc, tools_list_request)
    tools_list_response = _recv(proc)
    exchange.append({"direction": "client_to_server", "message": tools_list_request})
    exchange.append({"direction": "server_to_client", "message": tools_list_response})

    tools_call_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_claim_status", "arguments": {"claim_number": "CLM-2027-00201"}},
    }
    _send(proc, tools_call_request)
    tools_call_response = _recv(proc)
    exchange.append({"direction": "client_to_server", "message": tools_call_request})
    exchange.append({"direction": "server_to_client", "message": tools_call_response})

    proc.terminate()
    proc.wait(timeout=5)

    WIRE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WIRE_PATH.write_text(json.dumps(exchange, indent=2), encoding="utf-8")
    print(f"Wrote {WIRE_PATH}")
    print(json.dumps(exchange, indent=2))


if __name__ == "__main__":
    main()
