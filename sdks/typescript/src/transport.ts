/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { AcpMessage, messageToMap } from "./messages.js";
import { HttpSecurityPolicy, buildFetchOptions, validateHttpUrl } from "./httpSecurity.js";
import { JsonMap, parseJsonMap } from "./jsonSupport.js";
import { transportError } from "./errors.js";
import {
  AuthConfig,
  AuthType,
  TransportConfig,
  assertAllowedAuthTypes,
  authParameter,
  httpAuthHeaders,
  parseAuthConfig
} from "./transportAuth.js";

export interface TransportResponse {
  status_code: number;
  body?: JsonMap;
  raw_body: string;
}

export class TransportClient {
  private readonly fetchOptions: ReturnType<typeof buildFetchOptions>;
  private readonly allowedHttpAuthTypes: ReadonlySet<AuthType> = new Set([
    "none",
    "bearer",
    "basic",
    "mtls",
    "custom"
  ]);

  public constructor(
    private readonly timeoutSeconds: number,
    private readonly policy: HttpSecurityPolicy
  ) {
    this.fetchOptions = buildFetchOptions(policy);
  }

  private resolveHttpAuth(transportConfig?: Partial<TransportConfig>): AuthConfig | undefined {
    const auth = parseAuthConfig(transportConfig?.auth);
    assertAllowedAuthTypes(auth, this.allowedHttpAuthTypes, "HTTP/relay transport");
    return auth;
  }

  private fetchOptionsForAuth(auth: AuthConfig | undefined): ReturnType<typeof buildFetchOptions> {
    if (!auth || auth.type !== "mtls") {
      return this.fetchOptions;
    }
    const certFile = authParameter(auth, "cert_path", "mTLS auth");
    const keyFile = authParameter(auth, "key_path", "mTLS auth");
    const caFile = auth.parameters.ca_path?.trim() || this.policy.ca_file;
    return buildFetchOptions({
      ...this.policy,
      mtls_enabled: true,
      cert_file: certFile,
      key_file: keyFile,
      ca_file: caFile
    });
  }

  public async postJson(
    url: string,
    body: JsonMap,
    transportConfig?: Partial<TransportConfig>
  ): Promise<TransportResponse> {
    const auth = this.resolveHttpAuth(transportConfig);
    const mtlsEnabled = this.policy.mtls_enabled || auth?.type === "mtls";
    validateHttpUrl(url, this.policy.allow_insecure_http, mtlsEnabled, "HTTP transport request");
    const authHeaders = httpAuthHeaders(auth);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Math.max(1, this.timeoutSeconds) * 1000);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify(body),
        signal: controller.signal,
        ...this.fetchOptionsForAuth(auth)
      } as RequestInit);
      const rawBody = await response.text();
      let parsedBody: JsonMap | undefined;
      try {
        parsedBody = parseJsonMap(rawBody);
      } catch {
        parsedBody = undefined;
      }
      return {
        status_code: response.status,
        raw_body: rawBody,
        body: parsedBody
      };
    } catch (error) {
      throw transportError(`HTTP request failed: ${String(error)}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  public async sendToRelay(relayUrl: string, message: AcpMessage): Promise<JsonMap> {
    return this.sendToRelayWithConfig(relayUrl, message);
  }

  public async sendToRelayWithConfig(
    relayUrl: string,
    message: AcpMessage,
    transportConfig?: Partial<TransportConfig>
  ): Promise<JsonMap> {
    const relayEndpoint = relayUrl.endsWith("/") ? `${relayUrl}messages` : `${relayUrl}/messages`;
    const response = await this.postJson(relayEndpoint, messageToMap(message), transportConfig);
    if (response.status_code !== 200) {
      throw transportError(
        `Relay returned HTTP ${response.status_code} for message ${message.envelope.message_id}`
      );
    }
    if (!response.body) {
      throw transportError("Relay returned non-JSON response");
    }
    return response.body;
  }
}
