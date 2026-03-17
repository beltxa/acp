#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

RELAY_URL="${RELAY_URL:-http://localhost:8080}"
ACP_PYTHONPATH="${REPO_ROOT}/sdks/python:${REPO_ROOT}/cli"

JOHN_AGENT_ID="agent:john.chess@demo"
RICARDO_AGENT_ID="agent:ricardo.chess@demo"

JOHN_STORAGE="${JOHN_STORAGE:-${REPO_ROOT}/demos/identities/john}"
RICARDO_STORAGE="${RICARDO_STORAGE:-${REPO_ROOT}/demos/identities/ricardo}"

JOHN_ENDPOINT="${JOHN_ENDPOINT:-http://localhost:8088/api/v1/acp/messages}"
RICARDO_ENDPOINT="${RICARDO_ENDPOINT:-http://localhost:8089/api/v1/acp/messages}"

REGISTER_JOHN="${REGISTER_JOHN:-1}"
CLOUD_ENDPOINT="${CLOUD_ENDPOINT:-}"

acp_cmd() {
  if command -v acp >/dev/null 2>&1; then
    acp "$@"
  else
    PYTHONWARNINGS="ignore::RuntimeWarning" PYTHONPATH="${ACP_PYTHONPATH}" "${PYTHON_BIN}" -m acp_cli.main "$@"
  fi
}

ensure_identity() {
  local storage_dir="$1"
  local agent_id="$2"
  if ! acp_cmd --storage-dir "${storage_dir}" identity show --agent-id "${agent_id}" >/dev/null 2>&1; then
    echo "Missing identity for ${agent_id} in ${storage_dir}" >&2
    echo "Create demo identities first (see demos/scripts/start_demo.sh init-identities)." >&2
    return 1
  fi
}

echo "==> Verifying demo identities"
ensure_identity "${RICARDO_STORAGE}" "${RICARDO_AGENT_ID}"
ensure_identity "${JOHN_STORAGE}" "${JOHN_AGENT_ID}"

echo "==> Registering Ricardo identity in relay: ${RELAY_URL}"
acp_cmd \
  --storage-dir "${RICARDO_STORAGE}" \
  register put \
  --agent-id "${RICARDO_AGENT_ID}" \
  --relay "${RELAY_URL}" \
  --endpoint "${RICARDO_ENDPOINT}" \
  >/dev/null

if [[ "${REGISTER_JOHN}" == "1" ]]; then
  echo "==> Registering John identity in relay: ${RELAY_URL}"
  acp_cmd \
    --storage-dir "${JOHN_STORAGE}" \
    register put \
    --agent-id "${JOHN_AGENT_ID}" \
    --relay "${RELAY_URL}" \
    --endpoint "${JOHN_ENDPOINT}" \
    >/dev/null
fi

echo "==> Verifying relay registration for Ricardo"
acp_cmd \
  --storage-dir "${RICARDO_STORAGE}" \
  --json \
  register show \
  --agent-id "${RICARDO_AGENT_ID}" \
  --relay "${RELAY_URL}" \
  >/dev/null

echo "==> Refreshing John's discovery cache before relay lookup"
rm -f "${JOHN_STORAGE}/discovery_cache.json"

echo "==> Verifying John discovery of Ricardo through relay"
acp_cmd \
  --storage-dir "${JOHN_STORAGE}" \
  --json \
  discover get \
  --agent-id "${RICARDO_AGENT_ID}" \
  --relay-hint "${RELAY_URL}" \
  --scheme http \
  >/dev/null

if [[ -n "${CLOUD_ENDPOINT}" ]]; then
  echo "==> Updating Ricardo registration endpoint for cloud migration"
  acp_cmd \
    --storage-dir "${RICARDO_STORAGE}" \
    register update \
    --agent-id "${RICARDO_AGENT_ID}" \
    --relay "${RELAY_URL}" \
    --endpoint "${CLOUD_ENDPOINT}" \
    >/dev/null

  echo "==> Refreshing John's discovery cache before cloud re-lookup"
  rm -f "${JOHN_STORAGE}/discovery_cache.json"

  echo "==> Re-validating John discovery after cloud endpoint update"
  acp_cmd \
    --storage-dir "${JOHN_STORAGE}" \
    --json \
    discover get \
    --agent-id "${RICARDO_AGENT_ID}" \
    --relay-hint "${RELAY_URL}" \
    --scheme http \
    >/dev/null
fi

echo "Registry prewarm complete."
echo "Relay: ${RELAY_URL}"
echo "Registered: ${RICARDO_AGENT_ID}"
if [[ "${REGISTER_JOHN}" == "1" ]]; then
  echo "Registered: ${JOHN_AGENT_ID}"
fi
if [[ -n "${CLOUD_ENDPOINT}" ]]; then
  echo "Ricardo endpoint updated to cloud target: ${CLOUD_ENDPOINT}"
fi
