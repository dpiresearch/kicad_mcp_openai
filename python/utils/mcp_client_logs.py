"""Resolve MCP client log files for dev-mode session capture."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def resolve_mcp_client_log(server_name: str = "kicad") -> str | None:
    """Return the path to the MCP client log file, if it exists."""
    explicit = os.environ.get("KICAD_MCP_CLIENT_LOG")
    if explicit and os.path.exists(explicit):
        return explicit

    home = Path.home()
    system = platform.system()
    log_filename = f"mcp-server-{server_name}.log"

    candidates: list[Path] = [
        home / ".codex" / "logs" / log_filename,
        home / ".codex" / "logs" / "codex-tui.log",
    ]

    codex_logs = home / ".codex" / "logs"
    if codex_logs.is_dir():
        candidates.extend(sorted(codex_logs.glob("mcp*.log")))

    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Claude" / "logs" / log_filename)
    elif system == "Darwin":
        candidates.append(home / "Library" / "Logs" / "Claude" / log_filename)
    else:
        candidates.append(home / ".config" / "Claude" / "logs" / log_filename)

    for path in candidates:
        if path.exists():
            return str(path)
    return None
