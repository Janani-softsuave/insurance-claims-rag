from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import ROOT_DIR

CONFIG_PATH = ROOT_DIR / "mcp_config.json"


@dataclass
class ServerSpec:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]


def load_server_specs(config_path: Path | None = None) -> list[ServerSpec]:
    path = config_path or CONFIG_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs = []
    for entry in raw["servers"]:
        command = entry["command"]
        if command == "python":
            command = sys.executable
        specs.append(ServerSpec(name=entry["name"], command=command, args=entry["args"], env=entry.get("env", {})))
    return specs
