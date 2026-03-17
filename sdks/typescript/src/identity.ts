/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import {
  ACP_IDENTITY_VERSION,
  isSupportedTrustProfile
} from "./constants";
import {
  ed25519PublicFromPrivate,
  generateEd25519Keypair,
  generateX25519Keypair,
  signBytes,
  verifySignature,
  x25519PublicFromPrivate
} from "./crypto";
import { JsonMap, JsonValue, canonicalJsonBytes, parseJsonMap } from "./jsonSupport";
import { validationError } from "./errors";

export interface AgentIdentity {
  agent_id: string;
  signing_private_key: string;
  signing_public_key: string;
  encryption_private_key: string;
  encryption_public_key: string;
  signing_kid: string;
  encryption_kid: string;
}

export interface AgentIdParts {
  name: string;
  domain?: string;
}

export interface IdentityBundle {
  identity: AgentIdentity;
  identity_document: JsonMap;
}

const IDENTITY_FILE_NAME = "identity.json";
const IDENTITY_DOC_FILE_NAME = "identity_document.json";

export function parseAgentId(agentId: string): AgentIdParts {
  const match = /^agent:(?<name>[^@]+)(?:@(?<domain>.+))?$/.exec(agentId);
  if (!match?.groups?.name) {
    throw validationError(`Invalid agent identifier: ${agentId}`);
  }
  return {
    name: match.groups.name,
    domain: match.groups.domain || undefined
  };
}

export function sanitizeAgentId(agentId: string): string {
  return agentId
    .split("")
    .map((ch) => (/^[A-Za-z0-9._-]$/.test(ch) ? ch : "_"))
    .join("");
}

function identityPath(storageDir: string, agentId: string): string {
  return join(storageDir, sanitizeAgentId(agentId));
}

export function createIdentity(agentId: string): AgentIdentity {
  parseAgentId(agentId);
  const signing = generateEd25519Keypair();
  const encryption = generateX25519Keypair();
  return {
    agent_id: agentId,
    signing_private_key: signing.private_key,
    signing_public_key: signing.public_key,
    encryption_private_key: encryption.private_key,
    encryption_public_key: encryption.public_key,
    signing_kid: `sig-${randomUUID().replace(/-/g, "").slice(0, 12)}`,
    encryption_kid: `enc-${randomUUID().replace(/-/g, "").slice(0, 12)}`
  };
}

export function buildIdentityDocument(input: {
  identity: AgentIdentity;
  direct_endpoint?: string;
  relay_hints: string[];
  trust_profile: string;
  capabilities?: JsonMap;
  valid_days: number;
  amqp_service?: JsonMap;
  mqtt_service?: JsonMap;
  http_security_profile?: string;
  relay_security_profile?: string;
}): JsonMap {
  if (!isSupportedTrustProfile(input.trust_profile)) {
    throw validationError(`Unsupported trust profile: ${input.trust_profile}`);
  }
  const now = new Date();
  const validUntil = new Date(now.getTime() + Math.max(1, input.valid_days) * 24 * 60 * 60 * 1000);
  const service: JsonMap = {
    direct_endpoint: input.direct_endpoint ?? null,
    relay_hints: input.relay_hints
  };
  if (input.amqp_service) {
    service.amqp = input.amqp_service;
  }
  if (input.mqtt_service) {
    service.mqtt = input.mqtt_service;
  }
  if (input.direct_endpoint && input.http_security_profile) {
    service.http = {
      endpoint: input.direct_endpoint,
      security_profile: input.http_security_profile
    };
  }
  if (input.relay_hints[0] && input.relay_security_profile) {
    service.relay = {
      endpoint: input.relay_hints[0],
      security_profile: input.relay_security_profile
    };
  }
  const document: JsonMap = {
    acp_identity_version: ACP_IDENTITY_VERSION,
    agent_id: input.identity.agent_id,
    created_at: now.toISOString(),
    valid_until: validUntil.toISOString(),
    trust_profile: input.trust_profile,
    keys: {
      signing: {
        kid: input.identity.signing_kid,
        alg: "Ed25519",
        public_key: input.identity.signing_public_key
      },
      encryption: {
        kid: input.identity.encryption_kid,
        alg: "X25519",
        public_key: input.identity.encryption_public_key
      }
    },
    service,
    capabilities: input.capabilities ?? {}
  };
  const signature = signBytes(
    canonicalJsonBytes(document as JsonValue),
    input.identity.signing_private_key
  );
  document.signature = {
    algorithm: "Ed25519",
    signed_by: input.identity.signing_kid,
    value: signature
  };
  return document;
}

export function verifyIdentityDocument(identityDocument: JsonMap): boolean {
  for (const field of ["agent_id", "keys", "service", "signature", "valid_until"]) {
    if (!(field in identityDocument)) {
      return false;
    }
  }
  if (
    typeof identityDocument.trust_profile !== "string" ||
    !isSupportedTrustProfile(identityDocument.trust_profile)
  ) {
    return false;
  }
  if (typeof identityDocument.valid_until !== "string") {
    return false;
  }
  const expires = Date.parse(identityDocument.valid_until);
  if (Number.isNaN(expires) || expires <= Date.now()) {
    return false;
  }
  const signature = identityDocument.signature as JsonMap | undefined;
  const signingPublicKey = ((((identityDocument.keys as JsonMap).signing as JsonMap).public_key ??
    "") as string)
    .trim();
  const signatureValue = ((signature?.value ?? "") as string).trim();
  if (!signingPublicKey || !signatureValue) {
    return false;
  }
  const unsigned = { ...identityDocument };
  delete unsigned.signature;
  return verifySignature(canonicalJsonBytes(unsigned as JsonValue), signatureValue, signingPublicKey);
}

export function writeIdentity(storageDir: string, identity: AgentIdentity, identityDocument: JsonMap): void {
  const path = identityPath(storageDir, identity.agent_id);
  mkdirSync(path, { recursive: true });
  writeFileSync(join(path, IDENTITY_FILE_NAME), JSON.stringify(identity, null, 2), "utf-8");
  writeFileSync(join(path, IDENTITY_DOC_FILE_NAME), JSON.stringify(identityDocument, null, 2), "utf-8");
}

export function readIdentity(storageDir: string, agentId: string): IdentityBundle | undefined {
  const path = identityPath(storageDir, agentId);
  try {
    const identity = JSON.parse(readFileSync(join(path, IDENTITY_FILE_NAME), "utf-8")) as AgentIdentity;
    const identityDocument = parseJsonMap(readFileSync(join(path, IDENTITY_DOC_FILE_NAME), "utf-8"));
    return { identity, identity_document: identityDocument };
  } catch {
    return undefined;
  }
}

export function identityFromProvider(input: {
  agent_id: string;
  signing_private_key: string;
  encryption_private_key: string;
  signing_public_key?: string;
  encryption_public_key?: string;
  signing_kid?: string;
  encryption_kid?: string;
}): AgentIdentity {
  const signingPublicKey =
    input.signing_public_key ?? ed25519PublicFromPrivate(input.signing_private_key);
  const encryptionPublicKey =
    input.encryption_public_key ?? x25519PublicFromPrivate(input.encryption_private_key);
  return {
    agent_id: input.agent_id,
    signing_private_key: input.signing_private_key,
    signing_public_key: signingPublicKey,
    encryption_private_key: input.encryption_private_key,
    encryption_public_key: encryptionPublicKey,
    signing_kid: input.signing_kid ?? `sig-${randomUUID().replace(/-/g, "").slice(0, 12)}`,
    encryption_kid: input.encryption_kid ?? `enc-${randomUUID().replace(/-/g, "").slice(0, 12)}`
  };
}
