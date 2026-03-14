#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

DEMO_RUN_DIR="${REPO_ROOT}/demo/run"
RELAY_ENV_FILE="${REPO_ROOT}/demo/relay/.env"
RELAY_ENV_TEMPLATE="${REPO_ROOT}/demo/relay/.env.example"
RELAY_PID_FILE="${DEMO_RUN_DIR}/relay.pid"
RELAY_LOG_FILE="${DEMO_RUN_DIR}/relay.log"
RELAY_URL="${RELAY_URL:-http://localhost:8080}"

JOHN_AGENT_ID="agent:john.chess@demo"
RICARDO_AGENT_ID="agent:ricardo.chess@demo"
JOHN_STORAGE="${REPO_ROOT}/demo/identities/john"
RICARDO_STORAGE="${REPO_ROOT}/demo/identities/ricardo"

acp_cmd() {
  if command -v acp >/dev/null 2>&1; then
    acp "$@"
  else
    PYTHONWARNINGS="ignore::RuntimeWarning" PYTHONPATH="${REPO_ROOT}/acp-sdk-python" "${PYTHON_BIN}" -m acp_cli.main "$@"
  fi
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  init-identities      Create/recreate demo identities for John and Ricardo
  relay-up             Start relay with demo env config
  relay-down           Stop relay started by this script
  prewarm              Pre-warm relay registry and verify discovery
  run-john-direct      Run John's local agent in direct mode (port 8088)
  run-ricardo-direct   Run Ricardo's local agent in direct mode (port 8089)
  run-john-relay       Run John's local agent in relay mode (port 8088)
  run-ricardo-relay    Run Ricardo's local agent in relay mode (port 8089)
EOF
}

ensure_env_file() {
  if [[ ! -f "${RELAY_ENV_FILE}" ]]; then
    cp "${RELAY_ENV_TEMPLATE}" "${RELAY_ENV_FILE}"
  fi
}

init_identities() {
  rm -rf "${JOHN_STORAGE}" "${RICARDO_STORAGE}"

  acp_cmd \
    --storage-dir "${JOHN_STORAGE}" \
    identity create \
    --agent-id "${JOHN_AGENT_ID}" \
    --direct-endpoint "http://localhost:8088/api/v1/acp/messages" \
    --relay-hint "${RELAY_URL}" \
    --overwrite \
    >/dev/null

  acp_cmd \
    --storage-dir "${RICARDO_STORAGE}" \
    identity create \
    --agent-id "${RICARDO_AGENT_ID}" \
    --direct-endpoint "http://localhost:8089/api/v1/acp/messages" \
    --relay-hint "${RELAY_URL}" \
    --overwrite \
    >/dev/null

  REPO_ROOT="${REPO_ROOT}" PYTHONPATH="${REPO_ROOT}/acp-sdk-python" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

from acp.discovery import DiscoveryClient
from acp.identity import sanitize_agent_id

repo_root = Path(os.environ["REPO_ROOT"])
john_storage = repo_root / "demo" / "identities" / "john"
ricardo_storage = repo_root / "demo" / "identities" / "ricardo"

john_agent_id = "agent:john.chess@demo"
ricardo_agent_id = "agent:ricardo.chess@demo"

def load_doc(storage: Path, agent_id: str) -> dict:
    path = storage / sanitize_agent_id(agent_id) / "identity_document.json"
    return json.loads(path.read_text(encoding="utf-8"))

john_doc = load_doc(john_storage, john_agent_id)
ricardo_doc = load_doc(ricardo_storage, ricardo_agent_id)

john_discovery = DiscoveryClient(cache_path=john_storage / "discovery_cache.json", default_scheme="http")
ricardo_discovery = DiscoveryClient(cache_path=ricardo_storage / "discovery_cache.json", default_scheme="http")

john_discovery.seed(ricardo_doc)
ricardo_discovery.seed(john_doc)
PY

  echo "Demo identities created:"
  echo "  ${JOHN_STORAGE}"
  echo "  ${RICARDO_STORAGE}"
  echo "Discovery caches pre-seeded for direct stage."
}

relay_up() {
  mkdir -p "${DEMO_RUN_DIR}"
  ensure_env_file

  if [[ -f "${RELAY_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${RELAY_PID_FILE}")"
    if kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Relay is already running (pid ${pid})."
      return 0
    fi
    rm -f "${RELAY_PID_FILE}"
  fi

  set -a
  # shellcheck disable=SC1090
  source "${RELAY_ENV_FILE}"
  set +a

  local relay_pid
  relay_pid="$(
    REPO_ROOT="${REPO_ROOT}" \
    PYTHON_BIN="${PYTHON_BIN}" \
    RELAY_LOG_FILE="${RELAY_LOG_FILE}" \
    ACP_RELAY_HOST="${ACP_RELAY_HOST}" \
    ACP_RELAY_PORT="${ACP_RELAY_PORT}" \
    "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import os
import subprocess

repo_root = os.environ["REPO_ROOT"]
python_bin = os.environ["PYTHON_BIN"]
relay_log_file = os.environ["RELAY_LOG_FILE"]
relay_host = os.environ["ACP_RELAY_HOST"]
relay_port = os.environ["ACP_RELAY_PORT"]

cmd = [python_bin, "-m", "uvicorn", "app:app", "--host", relay_host, "--port", relay_port]
cwd = os.path.join(repo_root, "acp-relay")

with open(relay_log_file, "ab", buffering=0) as log_handle:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=log_handle,
        stderr=log_handle,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

print(process.pid)
PY
  )"
  echo "${relay_pid}" >"${RELAY_PID_FILE}"

  for _ in {1..20}; do
    if curl -fsS "${RELAY_URL}/health" >/dev/null 2>&1; then
      echo "Relay started: ${RELAY_URL}"
      echo "Log: ${RELAY_LOG_FILE}"
      return 0
    fi
    sleep 0.5
  done

  echo "Relay failed to start. See ${RELAY_LOG_FILE}" >&2
  return 1
}

relay_down() {
  if [[ ! -f "${RELAY_PID_FILE}" ]]; then
    echo "Relay is not running (no pid file)."
    return 0
  fi
  local pid
  pid="$(cat "${RELAY_PID_FILE}")"
  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" 2>/dev/null || true
    echo "Relay stopped (pid ${pid})."
  else
    echo "Relay pid ${pid} was not running."
  fi
  rm -f "${RELAY_PID_FILE}"
}

run_john_direct() {
  acp_cmd \
    --storage-dir "${JOHN_STORAGE}" \
    agent run \
    --agent-id "${JOHN_AGENT_ID}" \
    --transport direct \
    --port 8088
}

run_ricardo_direct() {
  acp_cmd \
    --storage-dir "${RICARDO_STORAGE}" \
    agent run \
    --agent-id "${RICARDO_AGENT_ID}" \
    --transport direct \
    --port 8089
}

run_john_relay() {
  acp_cmd \
    --storage-dir "${JOHN_STORAGE}" \
    agent run \
    --agent-id "${JOHN_AGENT_ID}" \
    --transport relay \
    --port 8088 \
    --relay "${RELAY_URL}"
}

run_ricardo_relay() {
  acp_cmd \
    --storage-dir "${RICARDO_STORAGE}" \
    agent run \
    --agent-id "${RICARDO_AGENT_ID}" \
    --transport relay \
    --port 8089 \
    --relay "${RELAY_URL}"
}

command="${1:-}"
case "${command}" in
  init-identities)
    init_identities
    ;;
  relay-up)
    relay_up
    ;;
  relay-down)
    relay_down
    ;;
  prewarm)
    "${SCRIPT_DIR}/prewarm_registry.sh"
    ;;
  run-john-direct)
    run_john_direct
    ;;
  run-ricardo-direct)
    run_ricardo_direct
    ;;
  run-john-relay)
    run_john_relay
    ;;
  run-ricardo-relay)
    run_ricardo_relay
    ;;
  *)
    usage
    exit 1
    ;;
esac
