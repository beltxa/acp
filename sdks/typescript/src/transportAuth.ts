/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { validationError } from "./errors.js";
import { JsonMap, JsonValue } from "./jsonSupport.js";

export type TransportProtocol = "http" | "mqtt" | "amqp" | "relay";
export type AuthType = "none" | "bearer" | "basic" | "mtls" | "username_password" | "custom";

export interface AuthConfig {
  type: AuthType;
  parameters: Record<string, string>;
}

export interface TransportConfig {
  protocol: TransportProtocol;
  endpoint: string;
  auth?: AuthConfig;
}

const SUPPORTED_AUTH_TYPES = new Set<AuthType>([
  "none",
  "bearer",
  "basic",
  "mtls",
  "username_password",
  "custom"
]);

function asStringRecord(value: unknown, context: string): Record<string, string> {
  if (value === null || value === undefined) {
    return {};
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw validationError(`${context} must be an object`);
  }
  const output: Record<string, string> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (item === null || item === undefined) {
      continue;
    }
    output[String(key)] = String(item);
  }
  return output;
}

export function parseAuthConfig(value: unknown): AuthConfig | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw validationError("Transport auth must be an object with fields: type, parameters");
  }
  const raw = value as Record<string, unknown>;
  const type = typeof raw.type === "string" ? raw.type.trim().toLowerCase() : "none";
  if (!SUPPORTED_AUTH_TYPES.has(type as AuthType)) {
    throw validationError(`Unsupported auth type: ${String(raw.type)}`);
  }
  const parameters = asStringRecord(raw.parameters, "Transport auth.parameters");
  return { type: type as AuthType, parameters };
}

export function authParameter(auth: AuthConfig, key: string, context: string): string {
  const value = auth.parameters[key];
  if (typeof value !== "string" || !value.trim()) {
    throw validationError(`${context} requires auth.parameters.${key}`);
  }
  return value.trim();
}

export function assertAllowedAuthTypes(
  auth: AuthConfig | undefined,
  allowed: ReadonlySet<AuthType>,
  context: string
): void {
  if (!auth) {
    return;
  }
  if (!allowed.has(auth.type)) {
    throw validationError(`${context} does not support auth type: ${auth.type}`);
  }
}

export function serializeAuthConfig(auth: AuthConfig | undefined): JsonMap | undefined {
  if (!auth) {
    return undefined;
  }
  const parameters: JsonMap = {};
  for (const [key, value] of Object.entries(auth.parameters)) {
    parameters[key] = value;
  }
  return {
    type: auth.type,
    parameters
  };
}

export function parseAuthFromService(service: JsonMap | undefined): AuthConfig | undefined {
  const raw = service?.auth;
  return parseAuthConfig(raw as JsonValue | undefined);
}

export function httpAuthHeaders(auth: AuthConfig | undefined): Record<string, string> {
  if (!auth || auth.type === "none" || auth.type === "mtls") {
    return {};
  }
  if (auth.type === "bearer") {
    const token = authParameter(auth, "token", "Bearer auth");
    return { Authorization: `Bearer ${token}` };
  }
  if (auth.type === "basic") {
    const username = authParameter(auth, "username", "Basic auth");
    const password = authParameter(auth, "password", "Basic auth");
    const encoded = Buffer.from(`${username}:${password}`, "utf-8").toString("base64");
    return { Authorization: `Basic ${encoded}` };
  }
  if (auth.type === "custom") {
    const header = auth.parameters.header;
    const value = auth.parameters.value;
    const scheme = auth.parameters.scheme;
    if (typeof header === "string" && header.trim()) {
      if (!value || !value.trim()) {
        throw validationError("Custom auth requires auth.parameters.value when header is set");
      }
      return { [header.trim()]: value.trim() };
    }
    if (typeof scheme === "string" && scheme.trim()) {
      if (!value || !value.trim()) {
        throw validationError("Custom auth requires auth.parameters.value when scheme is set");
      }
      return { Authorization: `${scheme.trim()} ${value.trim()}` };
    }
    throw validationError(
      "Custom auth requires either parameters.header + parameters.value or parameters.scheme + parameters.value"
    );
  }
  return {};
}
