from __future__ import annotations

import json
from pathlib import Path

from acp_cli.common import load_cli_config
from acp_cli.main import main


REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_VECTORS = REPO_ROOT / "tests" / "vectors" / "security"


def test_enterprise_https_fixture_loads_with_expected_fields(tmp_path: Path) -> None:
    fixture_path = SECURITY_VECTORS / "enterprise_profile_https.json"
    config_json = json.loads(fixture_path.read_text(encoding="utf-8"))
    ca_file = tmp_path / "enterprise-ca.pem"
    ca_file.write_text("ca", encoding="utf-8")
    config_json["ca_file"] = str(ca_file)
    config_json["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_json), encoding="utf-8")

    config, _selected_path = load_cli_config(str(config_path), None)
    assert config.key_provider == "vault"
    assert config.vault_url == "https://vault.company.net"
    assert config.vault_path == "secret/data/acp/identities"
    assert config.vault_token_env == "VAULT_TOKEN"
    assert config.allow_insecure_http is False
    assert config.allow_insecure_tls is False
    assert config.mtls_enabled is False


def test_enterprise_vault_mtls_fixture_validates_without_local_cert_files(tmp_path: Path, capsys) -> None:
    fixture_path = SECURITY_VECTORS / "enterprise_profile_vault_mtls.json"
    config_json = json.loads(fixture_path.read_text(encoding="utf-8"))
    ca_file = tmp_path / "enterprise-ca.pem"
    ca_file.write_text("ca", encoding="utf-8")
    config_json["ca_file"] = str(ca_file)
    config_json["storage_dir"] = str(tmp_path / "data")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_json), encoding="utf-8")

    code = main(["--config", str(config_path), "--json", "config", "validate"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
