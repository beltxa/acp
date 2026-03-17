#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python interpreter not found: ${PYTHON_BIN}" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/acp-quickstart.XXXXXX")"
VENV_DIR="${ACP_QUICKSTART_VENV:-${WORK_DIR}/venv}"
STORAGE_DIR="${ACP_QUICKSTART_STORAGE:-${WORK_DIR}/storage}"
CONFIG_FILE="${WORK_DIR}/acp-config.json"
LOG_FILE="${WORK_DIR}/receiver.log"
SENDER_AGENT_ID="${ACP_QUICKSTART_SENDER_ID:-agent:sender.bot@localhost:9010}"
RECEIVER_AGENT_ID="${ACP_QUICKSTART_RECEIVER_ID:-agent:receiver.bot@localhost:9011}"
RECEIVER_PORT="${ACP_QUICKSTART_RECEIVER_PORT:-9011}"
RELAY_URL="${ACP_QUICKSTART_RELAY_URL:-http://localhost:8080}"
RECEIVER_PID=""

cleanup() {
  if [[ -n "${RECEIVER_PID}" ]] && kill -0 "${RECEIVER_PID}" >/dev/null 2>&1; then
    kill "${RECEIVER_PID}" >/dev/null 2>&1 || true
    wait "${RECEIVER_PID}" 2>/dev/null || true
  fi
  if [[ -z "${ACP_QUICKSTART_VENV:-}" && -d "${WORK_DIR}" ]]; then
    rm -rf "${WORK_DIR}"
  fi
}
trap cleanup EXIT

SECONDS=0
echo "Creating Python virtual environment in ${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "Installing ACP SDK and CLI from this repository"
python -m pip install --upgrade pip >/dev/null
python -m pip install -e "${REPO_ROOT}/sdks/python" -e "${REPO_ROOT}/cli" fastapi uvicorn >/dev/null

echo "Creating local sender identity"
acp \
  --storage-dir "${STORAGE_DIR}" \
  --allow-insecure-http \
  identity create \
  --agent-id "${SENDER_AGENT_ID}" \
  --direct-endpoint "http://localhost:9010/acp/inbox" \
  --overwrite \
  >/dev/null

cat >"${CONFIG_FILE}" <<EOF
{
  "storage_dir": "${STORAGE_DIR}",
  "discovery_scheme": "http",
  "allow_insecure_http": true
}
EOF

echo "Starting demo receiver on port ${RECEIVER_PORT}"
python "${REPO_ROOT}/examples/run_agent_server.py" \
  --agent-id "${RECEIVER_AGENT_ID}" \
  --port "${RECEIVER_PORT}" \
  --public-host localhost \
  --relay-url "${RELAY_URL}" \
  --storage-dir "${STORAGE_DIR}" \
  --allow-insecure-http \
  >"${LOG_FILE}" 2>&1 &
RECEIVER_PID=$!

for _ in {1..30}; do
  if curl -fsS "http://localhost:${RECEIVER_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! curl -fsS "http://localhost:${RECEIVER_PORT}/health" >/dev/null 2>&1; then
  echo "Receiver failed to start. Log: ${LOG_FILE}" >&2
  exit 1
fi

echo "Sending ping message"
SEND_OUTPUT="$(
  acp \
    --config "${CONFIG_FILE}" \
    --storage-dir "${STORAGE_DIR}" \
    --allow-insecure-http \
    --json \
    message send \
    --from "${SENDER_AGENT_ID}" \
    --to "${RECEIVER_AGENT_ID}" \
    --payload-json '{"type":"ping"}' \
    --delivery-mode direct \
    --context quickstart-ping
)"

SEND_OUTPUT="${SEND_OUTPUT}" python - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["SEND_OUTPUT"])
outcomes = payload.get("outcomes", [])
if not outcomes:
    print("No delivery outcomes returned", file=sys.stderr)
    sys.exit(1)
allowed = {"DELIVERED", "ACKNOWLEDGED"}
states = [str(item.get("state")) for item in outcomes]
if any(state not in allowed for state in states):
    print(f"Unexpected delivery states: {states}", file=sys.stderr)
    sys.exit(1)
print(f"Ping delivered successfully: {states}")
PY

echo "Quickstart completed in ${SECONDS}s"
