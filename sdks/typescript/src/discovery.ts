/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { mkdirSync } from "node:fs";
import { discoveryError, validationError } from "./errors";
import { HttpSecurityPolicy, buildFetchOptions, validateHttpUrl } from "./httpSecurity";
import { parseAgentId, verifyIdentityDocument } from "./identity";
import { JsonMap, JsonValue, parseJsonMap, toJsonMap } from "./jsonSupport";
import {
  parseWellKnownDocument,
  resolveIdentityDocumentReference,
  wellKnownUrlFromBase
} from "./wellKnown";

interface CachedDocument {
  identity_document: JsonMap;
  fetched_at: string;
}

function cacheValid(identityDocument: JsonMap): boolean {
  const validUntil = identityDocument.valid_until;
  if (typeof validUntil !== "string") {
    return false;
  }
  const expires = Date.parse(validUntil);
  return Number.isFinite(expires) && expires > Date.now();
}

function extractIdentityDocument(body: JsonMap): JsonMap | undefined {
  if (body.identity_document && typeof body.identity_document === "object" && !Array.isArray(body.identity_document)) {
    return body.identity_document as JsonMap;
  }
  if (body.agent_id && body.keys && body.service) {
    return body;
  }
  return undefined;
}

export class DiscoveryClient {
  private readonly cache = new Map<string, CachedDocument>();
  private readonly registry = new Map<string, JsonMap>();
  private readonly fetchOptions: ReturnType<typeof buildFetchOptions>;

  public constructor(
    private readonly cache_path: string | undefined,
    private readonly default_scheme = "https",
    private readonly relay_hints: string[] = [],
    private readonly enterprise_directory_hints: string[] = [],
    private readonly timeout_seconds = 10,
    private readonly policy: HttpSecurityPolicy = {
      allow_insecure_http: false,
      allow_insecure_tls: false,
      mtls_enabled: false
    }
  ) {
    this.fetchOptions = buildFetchOptions(policy);
    this.loadCache();
  }

  public seed(identityDocument: JsonMap): void {
    const agentId = identityDocument.agent_id;
    if (typeof agentId !== "string" || !agentId.trim()) {
      return;
    }
    this.cache.set(agentId, {
      identity_document: identityDocument,
      fetched_at: new Date().toISOString()
    });
    this.persistCache();
  }

  public registerIdentityDocument(identityDocument: JsonMap): void {
    const agentId = identityDocument.agent_id;
    if (typeof agentId !== "string" || !agentId.trim()) {
      throw validationError("Identity document missing agent_id");
    }
    this.registry.set(agentId, identityDocument);
    this.cache.set(agentId, {
      identity_document: identityDocument,
      fetched_at: new Date().toISOString()
    });
    this.persistCache();
  }

  public async resolve(agentId: string): Promise<JsonMap> {
    if (this.registry.has(agentId)) {
      return this.registry.get(agentId) as JsonMap;
    }
    const cached = this.tryCache(agentId);
    if (cached) {
      return cached;
    }
    const wellKnown = await this.tryWellKnown(agentId);
    if (wellKnown) {
      this.cacheIdentity(agentId, wellKnown);
      return wellKnown;
    }
    const relayLookup = await this.tryHintLookups(this.relay_hints, agentId);
    if (relayLookup) {
      this.cacheIdentity(agentId, relayLookup);
      return relayLookup;
    }
    const directoryLookup = await this.tryHintLookups(this.enterprise_directory_hints, agentId);
    if (directoryLookup) {
      this.cacheIdentity(agentId, directoryLookup);
      return directoryLookup;
    }
    throw discoveryError(`Unable to resolve identity document for ${agentId}`);
  }

  public async resolveWellKnown(baseUrl: string, expectedAgentId?: string): Promise<JsonMap> {
    const wellKnownUrl = wellKnownUrlFromBase(baseUrl);
    const resolved = await this.resolveWellKnownUrl(wellKnownUrl, expectedAgentId);
    if (!resolved) {
      throw discoveryError(`Unable to resolve well-known metadata from ${wellKnownUrl}`);
    }
    const identityDocument = toJsonMap(resolved.identity_document as JsonValue);
    const agentId = identityDocument.agent_id;
    if (typeof agentId !== "string" || !agentId.trim()) {
      throw discoveryError("Well-known discovery returned identity document without agent_id");
    }
    this.cacheIdentity(agentId, identityDocument);
    return {
      ...resolved,
      well_known_url: wellKnownUrl
    };
  }

  private tryCache(agentId: string): JsonMap | undefined {
    const cached = this.cache.get(agentId);
    if (!cached) {
      return undefined;
    }
    if (cacheValid(cached.identity_document)) {
      return cached.identity_document;
    }
    this.cache.delete(agentId);
    this.persistCache();
    return undefined;
  }

  private async tryWellKnown(agentId: string): Promise<JsonMap | undefined> {
    const parts = parseAgentId(agentId);
    if (!parts.domain) {
      return undefined;
    }
    const wellKnownUrl = `${this.default_scheme}://${parts.domain}/.well-known/acp`;
    const resolved = await this.resolveWellKnownUrl(wellKnownUrl, agentId);
    if (!resolved) {
      return undefined;
    }
    return toJsonMap(resolved.identity_document as JsonValue);
  }

  private async tryHintLookups(hints: string[], agentId: string): Promise<JsonMap | undefined> {
    for (const hint of hints) {
      const url = `${hint.replace(/\/+$/, "")}/discover`;
      const body = await this.fetchJson(url, [["agent_id", agentId]], "Discovery hint lookup");
      if (!body) {
        continue;
      }
      const identityDocument = extractIdentityDocument(body);
      if (identityDocument && verifyIdentityDocument(identityDocument)) {
        return identityDocument;
      }
    }
    return undefined;
  }

  private async resolveWellKnownUrl(
    wellKnownUrl: string,
    expectedAgentId?: string
  ): Promise<JsonMap | undefined> {
    const body = await this.fetchJson(wellKnownUrl, undefined, "Discovery .well-known lookup");
    if (!body) {
      return undefined;
    }
    let wellKnown: JsonMap;
    try {
      wellKnown = parseWellKnownDocument(body);
    } catch {
      return undefined;
    }
    if (expectedAgentId && wellKnown.agent_id !== expectedAgentId) {
      return undefined;
    }
    const identityReference = resolveIdentityDocumentReference(wellKnown, wellKnownUrl);
    const identityBody = await this.fetchJson(
      identityReference,
      undefined,
      "Discovery identity document lookup"
    );
    if (!identityBody) {
      return undefined;
    }
    const identityDocument = extractIdentityDocument(identityBody);
    if (!identityDocument || !verifyIdentityDocument(identityDocument)) {
      return undefined;
    }
    if (expectedAgentId && identityDocument.agent_id !== expectedAgentId) {
      return undefined;
    }
    return {
      well_known: wellKnown,
      identity_document: identityDocument
    };
  }

  private async fetchJson(
    rawUrl: string,
    query: Array<[string, string]> | undefined,
    context: string
  ): Promise<JsonMap | undefined> {
    const parsed = validateHttpUrl(
      rawUrl,
      this.policy.allow_insecure_http,
      this.policy.mtls_enabled,
      context
    );
    if (query && query.length > 0) {
      for (const [key, value] of query) {
        parsed.searchParams.set(key, value);
      }
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Math.max(1, this.timeout_seconds) * 1000);
    try {
      const response = await fetch(parsed.toString(), {
        method: "GET",
        signal: controller.signal,
        ...this.fetchOptions
      } as RequestInit);
      if (response.status !== 200) {
        return undefined;
      }
      const rawBody = await response.text();
      return parseJsonMap(rawBody);
    } catch {
      return undefined;
    } finally {
      clearTimeout(timeout);
    }
  }

  private cacheIdentity(agentId: string, identityDocument: JsonMap): void {
    this.cache.set(agentId, {
      identity_document: identityDocument,
      fetched_at: new Date().toISOString()
    });
    this.persistCache();
  }

  private loadCache(): void {
    if (!this.cache_path || !existsSync(this.cache_path)) {
      return;
    }
    try {
      const raw = parseJsonMap(readFileSync(this.cache_path, "utf-8"));
      for (const [agentId, value] of Object.entries(raw)) {
        if (value && typeof value === "object" && !Array.isArray(value)) {
          const entry = value as JsonMap;
          const identityDocument = extractIdentityDocument(entry);
          if (identityDocument) {
            this.cache.set(agentId, {
              identity_document: identityDocument,
              fetched_at: typeof entry.fetched_at === "string" ? entry.fetched_at : new Date().toISOString()
            });
          }
        }
      }
    } catch {
      // Invalid cache is ignored.
    }
  }

  private persistCache(): void {
    if (!this.cache_path) {
      return;
    }
    try {
      mkdirSync(dirname(this.cache_path), { recursive: true });
      const serialized: JsonMap = {};
      for (const [agentId, entry] of this.cache.entries()) {
        serialized[agentId] = {
          identity_document: entry.identity_document,
          fetched_at: entry.fetched_at
        };
      }
      writeFileSync(this.cache_path, JSON.stringify(serialized, null, 2), "utf-8");
    } catch {
      // Cache persistence failures are tolerated.
    }
  }
}
