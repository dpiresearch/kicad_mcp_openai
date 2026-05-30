#!/usr/bin/env bash
set -euo pipefail

MODE=""
ASSUME_YES=0
SERVER_NAME="kicad"
CODEX_CONFIG_PATH=""

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME --verify [--name NAME] [--codex-config PATH]
  $SCRIPT_NAME --dry-run [--name NAME] [--codex-config PATH]
  $SCRIPT_NAME --apply [--name NAME] [--codex-config PATH] [--yes]

Options:
  --verify               Check prerequisites and print detected paths
  --dry-run              Show config and merged Codex config without writing
  --apply                Write/update Codex CLI config (~/.codex/config.toml)
  --yes                  Do not prompt before writing (only with --apply)
  --name NAME            MCP server name (default: kicad)
  --codex-config PATH    Path to Codex config file (default: ~/.codex/config.toml)
EOF
}

# --- Terminal formatting ---
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  RESET=$'\033[0m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  CYAN=$'\033[36m'
else
  BOLD="" DIM="" RESET="" GREEN="" YELLOW="" RED="" CYAN=""
fi

SYM_OK="${GREEN}✓${RESET}"
SYM_WARN="${YELLOW}⚠${RESET}"
SYM_FAIL="${RED}✗${RESET}"

fail() { echo "${SYM_FAIL} ${RED}Error:${RESET} $1" >&2; exit 1; }
info() { echo "${SYM_OK} $1"; }
warn() { echo "${SYM_WARN} ${YELLOW}$1${RESET}"; }

section() {
  echo
  echo "${DIM}────────────────────────────────────────────────────${RESET}"
  echo "${BOLD}${CYAN}$1${RESET}"
  echo "${DIM}────────────────────────────────────────────────────${RESET}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify)
      MODE="verify"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --name)
      [[ $# -ge 2 ]] || fail "--name requires a value"
      SERVER_NAME="$2"
      shift 2
      ;;
    --codex-config)
      [[ $# -ge 2 ]] || fail "--codex-config requires a value"
      CODEX_CONFIG_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$MODE" ]] || { usage; exit 1; }
[[ -n "$SERVER_NAME" ]] || fail "Server name must not be empty"

if [[ -z "$CODEX_CONFIG_PATH" ]]; then
  CODEX_CONFIG_PATH="$HOME/.codex/config.toml"
fi

case "$CODEX_CONFIG_PATH" in
  "~/"*)
    CODEX_CONFIG_PATH="$HOME/${CODEX_CONFIG_PATH#~/}"
    ;;
esac

CODEX_CONFIG_DIR="$(dirname "$CODEX_CONFIG_PATH")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/package.json" ]]; then
  REPO_ROOT="$SCRIPT_DIR"
else
  REPO_ROOT="$(pwd)"
fi

DIST_JS="$REPO_ROOT/dist/index.js"

DEFAULT_KICAD_PYTHON="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KICAD_PYTHON="${KICAD_PYTHON:-$DEFAULT_KICAD_PYTHON}"

command -v python3 >/dev/null 2>&1 || fail "python3 not found"
NODE_PATH="$(command -v node || true)"
[[ -n "$NODE_PATH" ]] || fail "node not found in PATH"

[[ -f "$DIST_JS" ]] || fail "Missing build artifact: $DIST_JS. Run 'npm install && npm run build' first."
[[ -x "$KICAD_PYTHON" ]] || fail "KiCad Python not found or not executable: $KICAD_PYTHON"

DETECT_JSON="$("$KICAD_PYTHON" - <<'PY'
import json, sys, sysconfig
result = {
    "python_executable": sys.executable,
    "python_version": sys.version.split()[0],
    "purelib": sysconfig.get_paths().get("purelib"),
    "pcbnew_ok": False,
    "pcbnew_version": None,
    "pcbnew_error": None,
}
try:
    import pcbnew
    result["pcbnew_ok"] = True
    if hasattr(pcbnew, "GetBuildVersion"):
        result["pcbnew_version"] = pcbnew.GetBuildVersion()
except Exception as e:
    result["pcbnew_error"] = repr(e)
print(json.dumps(result))
PY
)"

PYTHON_EXE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["python_executable"])' "$DETECT_JSON")"
PYTHON_VERSION="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["python_version"])' "$DETECT_JSON")"
PYTHONPATH_VALUE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["purelib"])' "$DETECT_JSON")"
PCBNEW_OK="$(python3 -c 'import json,sys; print("true" if json.loads(sys.argv[1])["pcbnew_ok"] else "false")' "$DETECT_JSON")"
PCBNEW_VERSION="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["pcbnew_version"] or "")' "$DETECT_JSON")"
PCBNEW_ERROR="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["pcbnew_error"] or "")' "$DETECT_JSON")"

if [[ "$PCBNEW_OK" != "true" ]]; then
  fail "KiCad Python could not import pcbnew. Details: $PCBNEW_ERROR"
fi

CONFIG_FRAGMENT_TOML="$(python3 - "$NODE_PATH" "$DIST_JS" "$KICAD_PYTHON" "$PYTHONPATH_VALUE" "$SERVER_NAME" <<'PY'
import sys

node_path, dist_js, kicad_python, pythonpath, server_name = sys.argv[1:6]
print(f"""[mcp_servers.{server_name}]
command = "{node_path}"
args = ["{dist_js}"]
enabled = true
startup_timeout_sec = 30
tool_timeout_sec = 300

[mcp_servers.{server_name}.env]
KICAD_PYTHON = "{kicad_python}"
PYTHONPATH = "{pythonpath}"
LOG_LEVEL = "info"
""")
PY
)"

show_detected() {
  section "Prerequisites"
  echo "  ${SYM_OK} python3          $(command -v python3)"
  echo "  ${SYM_OK} node             $NODE_PATH"
  echo "  ${SYM_OK} build artifact   $DIST_JS"
  echo "  ${SYM_OK} KiCad Python     $KICAD_PYTHON"
  echo "  ${SYM_OK} pcbnew import    $PCBNEW_VERSION"

  section "Configuration"
  echo "  Server name:       ${BOLD}$SERVER_NAME${RESET}"
  echo "  Repo root:         $REPO_ROOT"
  echo "  Python executable: $PYTHON_EXE"
  echo "  Python version:    $PYTHON_VERSION"
  echo "  PYTHONPATH:        $PYTHONPATH_VALUE"
  echo "  Codex config:      $CODEX_CONFIG_PATH"
}

merge_config() {
  python3 - "$CODEX_CONFIG_PATH" "$CONFIG_FRAGMENT_TOML" "$SERVER_NAME" <<'PY'
import json
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
fragment = sys.argv[2].rstrip() + "\n"
server_name = sys.argv[3]
section_prefix = f"[mcp_servers.{server_name}]"

existing = ""
status = {
    "config_exists": False,
    "had_entry": False,
}

if config_path.exists():
    status["config_exists"] = True
    existing = config_path.read_text(encoding="utf-8")
    if section_prefix in existing:
        status["had_entry"] = True
        pattern = re.compile(
            rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}(?:\.[^\]]+)?\][^\[]*"
        )
        existing = pattern.sub("", existing).rstrip() + "\n"

merged = (existing.rstrip() + "\n\n" if existing.strip() else "") + fragment
print(json.dumps({"status": status, "merged": merged}))
PY
}

if [[ "$MODE" == "verify" ]]; then
  show_detected
  section "Proposed Codex MCP entry ('$SERVER_NAME')"
  echo "$CONFIG_FRAGMENT_TOML"
  exit 0
fi

MERGE_RESULT="$(merge_config 2>&1)" || {
  echo "$MERGE_RESULT"
  exit 1
}

MERGED_TOML="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["merged"], end="")' <<<"$MERGE_RESULT")"
CONFIG_EXISTS="$(python3 -c 'import json,sys; print("true" if json.loads(sys.stdin.read())["status"]["config_exists"] else "false")' <<<"$MERGE_RESULT")"
HAD_ENTRY="$(python3 -c 'import json,sys; print("true" if json.loads(sys.stdin.read())["status"]["had_entry"] else "false")' <<<"$MERGE_RESULT")"

show_detected

section "Proposed MCP entry ('$SERVER_NAME')"
echo "$CONFIG_FRAGMENT_TOML"

section "Codex CLI config"
if [[ "$CONFIG_EXISTS" == "true" ]]; then
  if [[ "$HAD_ENTRY" == "true" ]]; then
    warn "Existing config already has mcp_servers.$SERVER_NAME — it will be replaced."
  else
    info "Existing config will be preserved; mcp_servers.$SERVER_NAME will be added."
  fi
else
  info "Config does not exist yet. A new file will be created."
fi
echo
echo "${DIM}Merged config preview:${RESET}"
echo "$MERGED_TOML"

if [[ "$MODE" == "dry-run" ]]; then
  exit 0
fi

mkdir -p "$CODEX_CONFIG_DIR"

if [[ $ASSUME_YES -ne 1 ]]; then
  echo
  read -r -p "Write this configuration to $CODEX_CONFIG_PATH ? [y/N] " REPLY
  case "$REPLY" in
    y|Y|yes|YES) ;;
    *)
      echo "Aborted."
      exit 0
      ;;
  esac
fi

if [[ -f "$CODEX_CONFIG_PATH" ]]; then
  BACKUP_PATH="${CODEX_CONFIG_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$CODEX_CONFIG_PATH" "$BACKUP_PATH"
  info "Backup written to ${DIM}$BACKUP_PATH${RESET}"
fi

TMP_PATH="${CODEX_CONFIG_PATH}.tmp.$$"
(umask 077 && printf '%s\n' "$MERGED_TOML" > "$TMP_PATH")
mv "$TMP_PATH" "$CODEX_CONFIG_PATH"

section "Done"
info "Codex CLI configuration updated successfully."

echo
echo "${BOLD}Next steps:${RESET}"
echo "  1. Restart Codex CLI (or start a new session)"
echo "  2. Verify the MCP server is listed:"
echo "     codex mcp list"
echo "  3. In Codex, ask it to use the ${BOLD}$SERVER_NAME${RESET} MCP server to run ${BOLD}check_kicad_ui${RESET}."
echo
