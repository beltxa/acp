/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { readFileSync } from "node:fs";
import { HttpSecurityPolicy, buildFetchOptions, validateHttpUrl } from "./httpSecurity";
import { JsonMap, toJsonMap } from "./jsonSupport";
import { keyProviderError } from "./errors";
import { readIdentity, sanitizeAgentId } from "./identity";

export interface IdentityKeyMaterial {
  signing_private_key: string;
  encryption_private_key: string;
  signing_public_key?: string;
  encryption_public_key?: string;
  signing_kid?: string;
  encryption_kid?: string;
}

export interface TlsMaterial {
  cert_file?: string;
  key_file?: string;
  ca_file?: string;
}

export type KeyProviderInfo = JsonMap;

export interface KeyProvider {
  loadIdentityKeys(agentId: string): Promise<IdentityKeyMaterial>;
  loadTlsMaterial(agentId: string): Promise<TlsMaterial>;
  loadCaBundle(agentId: string): Promise<string | undefined>;
  describe(): KeyProviderInfo;
}

function normalizeOptional(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

function secretValue(secret: JsonMap, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = secret[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

export class LocalKeyProvider implements KeyProvider {
  public constructor(
    private readonly storageDir: string,
    private readonly certFile?: string,
    private readonly keyFile?: string,
    private readonly caFile?: string
  ) {}

  public async loadIdentityKeys(agentId: string): Promise<IdentityKeyMaterial> {
    const bundle = readIdentity(this.storageDir, agentId);
    if (!bundle) {
      throw keyProviderError(`Local identity not found for ${agentId}`);
    }
    return {
      signing_private_key: bundle.identity.signing_private_key,
      encryption_private_key: bundle.identity.encryption_private_key,
      signing_public_key: bundle.identity.signing_public_key,
      encryption_public_key: bundle.identity.encryption_public_key,
      signing_kid: bundle.identity.signing_kid,
      encryption_kid: bundle.identity.encryption_kid
    };
  }

  public async loadTlsMaterial(_agentId: string): Promise<TlsMaterial> {
    return {
      cert_file: normalizeOptional(this.certFile),
      key_file: normalizeOptional(this.keyFile),
      ca_file: normalizeOptional(this.caFile)
    };
  }

  public async loadCaBundle(_agentId: string): Promise<string | undefined> {
    return normalizeOptional(this.caFile);
  }

  public describe(): KeyProviderInfo {
    return {
      provider: "local",
      storage_dir: this.storageDir
    };
  }
}

export class VaultKeyProvider implements KeyProvider {
  private readonly cache = new Map<string, JsonMap>();
  private readonly fetchOptions: ReturnType<typeof buildFetchOptions>;

  public constructor(
    private readonly vaultUrl: string,
    private readonly vaultPath: string,
    private readonly vaultTokenEnv = "VAULT_TOKEN",
    private readonly token?: string,
    private readonly timeoutSeconds = 10,
    caFile?: string,
    allowInsecureTls = false,
    allowInsecureHttp = false
  ) {
    if (!vaultUrl.trim()) {
      throw keyProviderError("vault_url is required for VaultKeyProvider");
    }
    if (!vaultPath.trim()) {
      throw keyProviderError("vault_path is required for VaultKeyProvider");
    }
    validateHttpUrl(vaultUrl, allowInsecureHttp, false, "Vault key provider URL");
    const policy: HttpSecurityPolicy = {
      allow_insecure_http: allowInsecureHttp,
      allow_insecure_tls: allowInsecureTls,
      mtls_enabled: false,
      ca_file: caFile,
      cert_file: undefined,
      key_file: undefined
    };
    this.fetchOptions = buildFetchOptions(policy);
  }

  public describe(): KeyProviderInfo {
    return {
      provider: "vault",
      vault_url: this.vaultUrl.replace(/\/+$/, ""),
      vault_path: this.vaultPath.replace(/^\/+/, ""),
      vault_token_env: this.vaultTokenEnv
    };
  }

  private resolveToken(): string | undefined {
    if (this.token && this.token.trim()) {
      return this.token.trim();
    }
    const envValue = process.env[this.vaultTokenEnv];
    return envValue?.trim() || undefined;
  }

  private secretPath(agentId: string): string {
    const sanitized = sanitizeAgentId(agentId);
    if (this.vaultPath.includes("{agent_id}")) {
      return this.vaultPath.replace("{agent_id}", sanitized);
    }
    return `${this.vaultPath.replace(/\/+$/, "")}/${sanitized}`;
  }

  private async loadSecret(agentId: string): Promise<JsonMap> {
    const path = this.secretPath(agentId);
    const cached = this.cache.get(path);
    if (cached) {
      return cached;
    }
    const token = this.resolveToken();
    if (!token) {
      throw keyProviderError(
        `Vault token is missing. Set token or environment variable ${this.vaultTokenEnv}.`
      );
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Math.max(1, this.timeoutSeconds) * 1000);
    try {
      const url = `${this.vaultUrl.replace(/\/+$/, "")}/v1/${path.replace(/^\/+/, "")}`;
      const response = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "X-Vault-Token": token
        },
        signal: controller.signal,
        ...this.fetchOptions
      } as RequestInit);
      if (response.status !== 200) {
        throw keyProviderError(`Vault returned HTTP ${response.status} for path ${path}`);
      }
      const parsed = toJsonMap((await response.json()) as JsonMap);
      const dataValue = parsed.data;
      if (!dataValue || typeof dataValue !== "object" || Array.isArray(dataValue)) {
        throw keyProviderError(`Vault response for path ${path} is missing data object`);
      }
      const topData = dataValue as JsonMap;
      const nestedData =
        topData.data && typeof topData.data === "object" && !Array.isArray(topData.data)
          ? (topData.data as JsonMap)
          : topData;
      this.cache.set(path, nestedData);
      return nestedData;
    } finally {
      clearTimeout(timeout);
    }
  }

  public async loadIdentityKeys(agentId: string): Promise<IdentityKeyMaterial> {
    const secret = await this.loadSecret(agentId);
    const signingPrivateKey = secretValue(secret, [
      "signing_key",
      "identity_signing_key",
      "signing_private_key"
    ]);
    const encryptionPrivateKey = secretValue(secret, [
      "encryption_key",
      "identity_encryption_key",
      "encryption_private_key"
    ]);
    if (!signingPrivateKey) {
      throw keyProviderError(`Vault secret for ${agentId} is missing signing_key`);
    }
    if (!encryptionPrivateKey) {
      throw keyProviderError(`Vault secret for ${agentId} is missing encryption_key`);
    }
    return {
      signing_private_key: signingPrivateKey,
      encryption_private_key: encryptionPrivateKey,
      signing_public_key: secretValue(secret, ["signing_public_key"]),
      encryption_public_key: secretValue(secret, ["encryption_public_key"]),
      signing_kid: secretValue(secret, ["signing_kid"]),
      encryption_kid: secretValue(secret, ["encryption_kid"])
    };
  }

  public async loadTlsMaterial(agentId: string): Promise<TlsMaterial> {
    const secret = await this.loadSecret(agentId);
    return {
      cert_file: secretValue(secret, ["tls_cert_file", "tls_cert", "cert_file"]),
      key_file: secretValue(secret, ["tls_key_file", "tls_key", "key_file"]),
      ca_file: secretValue(secret, ["ca_bundle_file", "ca_file", "ca_bundle"])
    };
  }

  public async loadCaBundle(agentId: string): Promise<string | undefined> {
    const secret = await this.loadSecret(agentId);
    return secretValue(secret, ["ca_bundle_file", "ca_file", "ca_bundle"]);
  }
}

export async function readCaFile(path: string | undefined): Promise<string | undefined> {
  if (!path) {
    return undefined;
  }
  return readFileSync(path, "utf-8");
}
