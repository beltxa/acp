import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { JsonMap } from "../src/jsonSupport.js";
import { defaultAgentOptions, optionsFromConfigMap, optionsToConfigMap } from "../src/options.js";

const VECTORS_DIR = join(process.cwd(), "..", "tests", "vectors", "security");

function loadFixture(name: string): JsonMap {
  return JSON.parse(readFileSync(join(VECTORS_DIR, name), "utf-8")) as JsonMap;
}

describe("Security profile compatibility", () => {
  it("reads shared security https fixture with expected schema", () => {
    const fixture = loadFixture("security_profile_https.json");
    const options = optionsFromConfigMap(fixture);
    expect(options.key_provider).toBe("vault");
    expect(options.vault_url).toBe("https://vault.company.net");
    expect(options.vault_path).toBe("secret/data/acp/identities");
    expect(options.vault_token_env).toBe("VAULT_TOKEN");
    expect(options.allow_insecure_http).toBe(false);
    expect(options.allow_insecure_tls).toBe(false);
    expect(options.mtls_enabled).toBe(false);
  });

  it("reads shared security vault + mtls fixture", () => {
    const fixture = loadFixture("security_profile_vault_mtls.json");
    const options = optionsFromConfigMap(fixture);
    expect(options.key_provider).toBe("vault");
    expect(options.mtls_enabled).toBe(true);
    expect(options.ca_file).toBe("/etc/acp/ca/security-profile-ca.pem");
    expect(options.cert_file).toBeUndefined();
    expect(options.key_file).toBeUndefined();
  });

  it("exports aligned security profile fields", () => {
    const options = {
      ...defaultAgentOptions(),
      key_provider: "vault" as const,
      vault_url: "https://vault.company.net",
      vault_path: "secret/data/acp/identities",
      vault_token_env: "VAULT_TOKEN",
      allow_insecure_http: false,
      allow_insecure_tls: false,
      mtls_enabled: true,
      ca_file: "/etc/acp/ca/security-profile-ca.pem"
    };
    const exported = optionsToConfigMap(options);
    expect(exported.key_provider).toBe("vault");
    expect(exported.vault_url).toBe("https://vault.company.net");
    expect(exported.vault_path).toBe("secret/data/acp/identities");
    expect(exported.vault_token_env).toBe("VAULT_TOKEN");
    expect(exported.allow_insecure_http).toBe(false);
    expect(exported.allow_insecure_tls).toBe(false);
    expect(exported.mtls_enabled).toBe(true);
    expect(exported.ca_file).toBe("/etc/acp/ca/security-profile-ca.pem");
  });
});
