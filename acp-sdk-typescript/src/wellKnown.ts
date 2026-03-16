import { ACP_VERSION, DEFAULT_IDENTITY_DOCUMENT_PATH } from "./constants.js";
import { JsonMap, JsonValue, toJsonMap } from "./jsonSupport.js";
import { validationError } from "./errors.js";

export const WELL_KNOWN_PATH = "/.well-known/acp";
export const SUPPORTED_WELL_KNOWN_VERSION = ACP_VERSION;
export const SUPPORTED_SECURITY_PROFILES = ["http", "https", "mtls", "https+mtls"] as const;

export function wellKnownUrlFromBase(baseUrl: string): string {
  const normalized = baseUrl.trim();
  if (!normalized) {
    throw validationError("base_url is required");
  }
  if (normalized.endsWith(WELL_KNOWN_PATH)) {
    return normalized;
  }
  return `${normalized.replace(/\/+$/, "")}${WELL_KNOWN_PATH}`;
}

export function identityDocumentUrlFromBase(baseUrl: string): string {
  const normalized = baseUrl.trim();
  if (!normalized) {
    throw validationError("base_url is required");
  }
  return `${normalized.replace(/\/+$/, "")}${DEFAULT_IDENTITY_DOCUMENT_PATH}`;
}

function inferSecurityProfile(transports: JsonMap): string {
  for (const transportName of ["http", "relay"]) {
    const transport = transports[transportName];
    if (transport && typeof transport === "object" && !Array.isArray(transport)) {
      const securityProfile = (transport as JsonMap).security_profile;
      if (typeof securityProfile === "string" && securityProfile.trim()) {
        return securityProfile.trim();
      }
    }
  }
  const endpoint = (((transports.http as JsonMap | undefined) ?? {}).endpoint as string | undefined) ?? "";
  if (endpoint.startsWith("https://")) {
    return "https";
  }
  if (endpoint.startsWith("http://")) {
    return "http";
  }
  return "https";
}

function validateIdentityDocumentReference(reference: string): void {
  try {
    const parsed = new URL(reference);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw validationError("identity_document URL must use http or https");
    }
    if (!parsed.hostname.trim()) {
      throw validationError("identity_document URL is missing host");
    }
    return;
  } catch {
    if (!reference.startsWith("/")) {
      throw validationError("identity_document URL must be absolute http(s) or root-relative path");
    }
  }
}

function validateTransports(transports: JsonMap): void {
  for (const [transportName, transportValue] of Object.entries(transports)) {
    if (!transportValue || typeof transportValue !== "object" || Array.isArray(transportValue)) {
      throw validationError(`Well-known transport hint ${transportName} must be an object`);
    }
    const hint = transportValue as JsonMap;
    if (hint.endpoint !== undefined) {
      if (typeof hint.endpoint !== "string") {
        throw validationError(`Well-known transport hint ${transportName}.endpoint must be a string`);
      }
      const endpoint = hint.endpoint.trim();
      try {
        const parsed = new URL(endpoint);
        if (
          (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
          !parsed.hostname.trim()
        ) {
          throw validationError(
            `Well-known transport hint ${transportName}.endpoint must be an absolute http(s) URL`
          );
        }
      } catch {
        throw validationError(
          `Well-known transport hint ${transportName}.endpoint must be an absolute http(s) URL`
        );
      }
    }
    if (hint.security_profile !== undefined) {
      if (
        typeof hint.security_profile !== "string" ||
        !SUPPORTED_SECURITY_PROFILES.includes(hint.security_profile as (typeof SUPPORTED_SECURITY_PROFILES)[number])
      ) {
        throw validationError(`Well-known transport hint ${transportName}.security_profile is invalid`);
      }
    }
  }
}

export function buildWellKnownDocument(input: {
  identity_document: JsonMap;
  base_url: string;
  identity_document_url?: string;
  version?: string;
}): JsonMap {
  const agentId = input.identity_document.agent_id;
  if (typeof agentId !== "string" || !agentId.trim()) {
    throw validationError("identity_document.agent_id is required");
  }
  const version = input.version ?? SUPPORTED_WELL_KNOWN_VERSION;
  if (version !== SUPPORTED_WELL_KNOWN_VERSION) {
    throw validationError(
      `Unsupported well-known version ${version}; expected ${SUPPORTED_WELL_KNOWN_VERSION}`
    );
  }

  const serviceRaw = input.identity_document.service;
  const service =
    serviceRaw && typeof serviceRaw === "object" && !Array.isArray(serviceRaw)
      ? (serviceRaw as JsonMap)
      : {};
  const capabilitiesRaw = input.identity_document.capabilities;
  const capabilities =
    capabilitiesRaw && typeof capabilitiesRaw === "object" && !Array.isArray(capabilitiesRaw)
      ? (capabilitiesRaw as JsonMap)
      : {};

  const transports: JsonMap = {};
  const directEndpoint = service.direct_endpoint;
  if (typeof directEndpoint === "string" && directEndpoint.trim()) {
    const httpHint: JsonMap = { endpoint: directEndpoint.trim() };
    const httpSecurityProfile =
      service.http && typeof service.http === "object" && !Array.isArray(service.http)
        ? (service.http as JsonMap).security_profile
        : undefined;
    if (typeof httpSecurityProfile === "string" && httpSecurityProfile.trim()) {
      httpHint.security_profile = httpSecurityProfile.trim();
    }
    transports.http = httpHint;
  }
  if (Array.isArray(service.relay_hints)) {
    const relayHints = service.relay_hints
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    if (relayHints.length > 0) {
      const relayHint: JsonMap = { endpoint: relayHints[0] };
      const relaySecurityProfile =
        service.relay && typeof service.relay === "object" && !Array.isArray(service.relay)
          ? (service.relay as JsonMap).security_profile
          : undefined;
      if (typeof relaySecurityProfile === "string" && relaySecurityProfile.trim()) {
        relayHint.security_profile = relaySecurityProfile.trim();
      }
      if (relayHints.length > 1) {
        relayHint.hints = relayHints;
      }
      transports.relay = relayHint;
    }
  }
  if (service.amqp && typeof service.amqp === "object" && !Array.isArray(service.amqp)) {
    transports.amqp = service.amqp as JsonValue;
  }
  if (service.mqtt && typeof service.mqtt === "object" && !Array.isArray(service.mqtt)) {
    transports.mqtt = service.mqtt as JsonValue;
  }

  const identityReference = input.identity_document_url ?? identityDocumentUrlFromBase(input.base_url);
  validateIdentityDocumentReference(identityReference);
  const doc: JsonMap = {
    agent_id: agentId,
    identity_document: identityReference,
    transports,
    version,
    security_profile: inferSecurityProfile(transports)
  };

  const supportsRaw = capabilities.supports;
  if (supportsRaw && typeof supportsRaw === "object" && !Array.isArray(supportsRaw)) {
    const supported = Object.entries(supportsRaw as JsonMap)
      .filter(([, enabled]) => Boolean(enabled))
      .map(([name]) => name)
      .sort();
    doc.capabilities = supported;
  }
  return doc;
}

export function parseWellKnownDocument(value: JsonValue): JsonMap {
  const map = toJsonMap(value);
  if (typeof map.agent_id !== "string" || !map.agent_id.trim()) {
    throw validationError("Well-known response missing agent_id");
  }
  if (typeof map.version !== "string" || map.version !== SUPPORTED_WELL_KNOWN_VERSION) {
    throw validationError(
      `Well-known response version must be ${SUPPORTED_WELL_KNOWN_VERSION}`
    );
  }
  if (typeof map.identity_document !== "string" || !map.identity_document.trim()) {
    throw validationError("Well-known response identity_document must be a URL string");
  }
  validateIdentityDocumentReference(map.identity_document);
  const transports = toJsonMap(map.transports);
  validateTransports(transports);
  if (map.security_profile !== undefined) {
    if (
      typeof map.security_profile !== "string" ||
      !SUPPORTED_SECURITY_PROFILES.includes(
        map.security_profile as (typeof SUPPORTED_SECURITY_PROFILES)[number]
      )
    ) {
      throw validationError("Well-known response security_profile is invalid");
    }
  }
  return map;
}

export function resolveIdentityDocumentReference(wellKnown: JsonMap, sourceUrl: string): string {
  const reference = wellKnown.identity_document;
  if (typeof reference !== "string" || !reference.trim()) {
    throw validationError("Well-known response identity_document reference is invalid");
  }
  validateIdentityDocumentReference(reference);
  try {
    return new URL(reference).toString();
  } catch {
    return new URL(reference, sourceUrl).toString();
  }
}
