/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { AgentCapabilities } from "./capabilities.js";
import { ACP_VERSION, DEFAULT_CRYPTO_SUITE } from "./constants.js";
import {
  signBytes,
  decryptForRecipient,
  encryptForRecipients,
  signProtectedPayload,
  verifyProtectedPayloadSignature
} from "./crypto.js";
import { DiscoveryClient } from "./discovery.js";
import {
  FailReason,
  processingError,
  transportError,
  validationError,
  keyProviderError
} from "./errors.js";
import { HttpSecurityPolicy, validateHttpClientPolicy, validateHttpUrl, warnIfInsecureHttpUsed } from "./httpSecurity.js";
import {
  AgentIdentity,
  buildIdentityDocument,
  createIdentity,
  identityFromProvider,
  parseAgentId,
  readIdentity,
  verifyIdentityDocument,
  writeIdentity
} from "./identity.js";
import { JsonMap, JsonValue, canonicalJsonBytes, toJsonMap } from "./jsonSupport.js";
import {
  AcpMessage,
  DeliveryMode,
  DeliveryOutcome,
  DeliveryState,
  Envelope,
  MessageClass,
  SendResult,
  buildAckPayload,
  buildEnvelope,
  buildFailPayload,
  isExpired,
  messageToMap,
  parseAcpMessage,
  parseMessageClass
} from "./messages.js";
import { AmqpTransportClient } from "./amqpTransport.js";
import { MqttTransportClient } from "./mqttTransport.js";
import { AcpAgentOptions, defaultAgentOptions } from "./options.js";
import { KeyProvider, KeyProviderInfo, LocalKeyProvider, VaultKeyProvider } from "./keyProvider.js";
import { TransportClient, TransportResponse } from "./transport.js";
import { AuthConfig, AuthType, assertAllowedAuthTypes, parseAuthConfig } from "./transportAuth.js";
import { buildWellKnownDocument } from "./wellKnown.js";

export interface InboundResult {
  state: DeliveryState;
  reason_code?: string;
  detail?: string;
  decrypted_payload?: JsonMap;
  response_message?: JsonMap;
}

export interface DecryptedMessage {
  message: AcpMessage;
  payload: JsonMap;
}

export interface CapabilityRequestResult {
  result: SendResult;
  capabilities?: JsonMap;
}

type InboundHandler = (payload: JsonMap, envelope: Envelope) => JsonMap | undefined;

interface ResolvedRecipient {
  recipient: string;
  public_key: string;
  channel: "direct" | "relay" | "amqp" | "mqtt";
  endpoint?: string;
  http_auth?: AuthConfig;
  amqp_service?: JsonMap;
  mqtt_service?: JsonMap;
}

interface ChannelChoice {
  channel?: "direct" | "relay" | "amqp" | "mqtt";
  endpoint?: string;
  amqp_service?: JsonMap;
  mqtt_service?: JsonMap;
  detail?: string;
}

class DedupStore {
  private readonly processed = new Map<string, number>();

  public constructor(private readonly ttlMs: number) {}

  public isDuplicate(messageId: string): boolean {
    this.cleanup();
    return this.processed.has(messageId);
  }

  public markProcessed(messageId: string): void {
    this.processed.set(messageId, Date.now());
  }

  private cleanup(): void {
    const now = Date.now();
    for (const [messageId, timestamp] of this.processed.entries()) {
      if (now - timestamp > this.ttlMs) {
        this.processed.delete(messageId);
      }
    }
  }
}

function firstNonBlank(...values: Array<string | undefined>): string | undefined {
  for (const value of values) {
    if (value && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function failedOutcome(recipient: string, reasonCode: string, detail: string): DeliveryOutcome {
  return {
    recipient,
    state: "FAILED",
    reason_code: reasonCode,
    detail
  };
}

function toPublicKeyMap(targets: ResolvedRecipient[]): Record<string, string> {
  const output: Record<string, string> = {};
  for (const target of targets) {
    output[target.recipient] = target.public_key;
  }
  return output;
}

const HTTP_AUTH_TYPES: ReadonlySet<AuthType> = new Set(["none", "bearer", "basic", "mtls", "custom"]);
const BROKER_AUTH_TYPES: ReadonlySet<AuthType> = new Set([
  "none",
  "username_password",
  "mtls",
  "custom"
]);

function extractHttpAuth(identityDocument: JsonMap): AuthConfig | undefined {
  const serviceRaw = identityDocument.service;
  const service = serviceRaw && typeof serviceRaw === "object" && !Array.isArray(serviceRaw) ? (serviceRaw as JsonMap) : {};
  const httpRaw = service.http;
  const httpService = httpRaw && typeof httpRaw === "object" && !Array.isArray(httpRaw) ? (httpRaw as JsonMap) : undefined;
  const auth = parseAuthConfig(httpService?.auth);
  assertAllowedAuthTypes(auth, HTTP_AUTH_TYPES, "Recipient HTTP transport");
  return auth;
}

function buildLocalAmqpService(agentId: string, options: AcpAgentOptions, auth?: AuthConfig): JsonMap | undefined {
  if (!options.amqp_broker_url) {
    return undefined;
  }
  return AmqpTransportClient.buildServiceHint(agentId, options.amqp_broker_url, options.amqp_exchange, auth);
}

function buildLocalMqttService(agentId: string, options: AcpAgentOptions, auth?: AuthConfig): JsonMap | undefined {
  if (!options.mqtt_broker_url) {
    return undefined;
  }
  return MqttTransportClient.buildServiceHint(
    agentId,
    options.mqtt_broker_url,
    undefined,
    options.mqtt_qos,
    options.mqtt_topic_prefix,
    auth
  );
}

function applyHttpSecurityProfile(identityDocument: JsonMap, mtlsEnabled: boolean): void {
  const serviceRaw = identityDocument.service;
  const service = serviceRaw && typeof serviceRaw === "object" && !Array.isArray(serviceRaw) ? (serviceRaw as JsonMap) : {};
  const directEndpoint = service.direct_endpoint;
  if (typeof directEndpoint === "string" && directEndpoint.trim()) {
    service.http = {
      endpoint: directEndpoint.trim(),
      security_profile: mtlsEnabled ? "mtls" : directEndpoint.startsWith("https://") ? "https" : "http"
    };
  }
  if (Array.isArray(service.relay_hints) && service.relay_hints.length > 0) {
    const endpoint = typeof service.relay_hints[0] === "string" ? service.relay_hints[0] : undefined;
    if (endpoint) {
      service.relay = {
        endpoint,
        security_profile: mtlsEnabled ? "mtls" : endpoint.startsWith("https://") ? "https" : "http"
      };
    }
  }
  identityDocument.service = service;
}

function resignIdentityDocument(identityDocument: JsonMap, identity: AgentIdentity): void {
  const unsigned: JsonMap = { ...identityDocument };
  delete unsigned.signature;
  identityDocument.signature = {
    algorithm: "Ed25519",
    signed_by: identity.signing_kid,
    value: signBytes(canonicalJsonBytes(unsigned as JsonValue), identity.signing_private_key)
  };
}

function parseReasonForCapabilityMismatch(reason?: string): FailReason {
  const normalized = (reason ?? "").toLowerCase();
  if (normalized.includes("protocol")) {
    return "UNSUPPORTED_VERSION";
  }
  if (normalized.includes("crypto")) {
    return "UNSUPPORTED_CRYPTO_SUITE";
  }
  if (normalized.includes("profile")) {
    return "UNSUPPORTED_PROFILE";
  }
  return "POLICY_REJECTED";
}

function deliveryStateFromResponse(
  statusCode: number,
  responseClass?: MessageClass,
  reasonCode?: string
): DeliveryState {
  if (statusCode >= 200 && statusCode < 300) {
    if (responseClass === "FAIL") {
      if (reasonCode === "EXPIRED_MESSAGE") {
        return "EXPIRED";
      }
      if (reasonCode === "POLICY_REJECTED") {
        return "DECLINED";
      }
      return "FAILED";
    }
    if (responseClass === "ACK" || responseClass === "CAPABILITIES") {
      return "ACKNOWLEDGED";
    }
    return "DELIVERED";
  }
  if (statusCode === 410) {
    return "EXPIRED";
  }
  if ([401, 403, 409, 422].includes(statusCode)) {
    return "DECLINED";
  }
  return "FAILED";
}

function outcomeFromHttpResponse(recipient: string, response: TransportResponse): DeliveryOutcome {
  const body = response.body;
  const responseMessage =
    body?.response_message && typeof body.response_message === "object" && !Array.isArray(body.response_message)
      ? (body.response_message as JsonMap)
      : undefined;
  const responseClass = parseMessageClass(
    responseMessage && responseMessage.envelope && typeof responseMessage.envelope === "object"
      ? ((responseMessage.envelope as JsonMap).message_class as string | undefined)
      : undefined
  );
  const reasonCode = typeof body?.reason_code === "string" ? body.reason_code : undefined;
  const detail =
    typeof body?.detail === "string"
      ? body.detail
      : response.status_code >= 400
        ? `Recipient HTTP ${response.status_code}`
        : undefined;
  return {
    recipient,
    state: deliveryStateFromResponse(response.status_code, responseClass, reasonCode),
    status_code: response.status_code,
    response_class: responseClass,
    reason_code: reasonCode,
    detail,
    response_message: responseMessage
  };
}

export class AcpAgent {
  private readonly dedup = new DedupStore(60 * 60 * 1000);
  private delivery_states = new Map<string, Map<string, string>>();

  private constructor(
    public identity: AgentIdentity,
    public identity_document: JsonMap,
    public discovery: DiscoveryClient,
    public transport: TransportClient,
    public amqp_transport: AmqpTransportClient | undefined,
    public mqtt_transport: MqttTransportClient | undefined,
    public capabilities: AgentCapabilities,
    public storage_dir: string,
    public trust_profile: string,
    public relay_url: string,
    public default_delivery_mode: DeliveryMode,
    public key_provider_info: KeyProviderInfo,
    private readonly direct_transport_auth: AuthConfig | undefined,
    private readonly relay_transport_auth: AuthConfig | undefined
  ) {}

  public static async loadOrCreate(
    agentId: string,
    optionsInput?: Partial<AcpAgentOptions>
  ): Promise<AcpAgent> {
    parseAgentId(agentId);
    const options: AcpAgentOptions = { ...defaultAgentOptions(), ...optionsInput };
    mkdirSync(options.storage_dir, { recursive: true });

    const keyProvider = await AcpAgent.resolveKeyProvider(options);
    const keyProviderInfo = keyProvider.describe();
    const providerIdentityKeys = await keyProvider.loadIdentityKeys(agentId).catch(() => undefined);
    const providerTls = await keyProvider.loadTlsMaterial(agentId).catch(() => ({} as JsonMap));
    const providerCa = await keyProvider.loadCaBundle(agentId).catch(() => undefined);
    const externalKeyProvider = keyProviderInfo.provider === "vault";

    const effectiveCaFile = firstNonBlank(options.ca_file, providerTls.ca_file as string | undefined, providerCa);
    const effectiveCertFile = firstNonBlank(options.cert_file, providerTls.cert_file as string | undefined);
    const effectiveKeyFile = firstNonBlank(options.key_file, providerTls.key_file as string | undefined);
    const policy: HttpSecurityPolicy = {
      allow_insecure_http: options.allow_insecure_http,
      allow_insecure_tls: options.allow_insecure_tls,
      mtls_enabled: options.mtls_enabled,
      ca_file: effectiveCaFile,
      cert_file: effectiveCertFile,
      key_file: effectiveKeyFile
    };
    validateHttpClientPolicy(policy, "Agent HTTP security configuration");
    if (options.endpoint) {
      validateHttpUrl(
        options.endpoint,
        policy.allow_insecure_http,
        policy.mtls_enabled,
        "Agent direct endpoint configuration"
      );
      if (policy.allow_insecure_http) {
        warnIfInsecureHttpUsed(options.endpoint, "Agent direct endpoint configuration");
      }
    }
    validateHttpUrl(options.relay_url, policy.allow_insecure_http, policy.mtls_enabled, "Agent relay URL configuration");
    for (const relayHint of options.relay_hints) {
      validateHttpUrl(relayHint, policy.allow_insecure_http, policy.mtls_enabled, "Agent relay hint configuration");
    }
    for (const directoryHint of options.enterprise_directory_hints) {
      validateHttpUrl(
        directoryHint,
        policy.allow_insecure_http,
        policy.mtls_enabled,
        "Agent enterprise directory hint configuration"
      );
    }

    const directTransportAuth = parseAuthConfig(options.direct_transport_auth);
    assertAllowedAuthTypes(directTransportAuth, HTTP_AUTH_TYPES, "Agent direct transport");
    const relayTransportAuth = parseAuthConfig(options.relay_transport_auth);
    assertAllowedAuthTypes(relayTransportAuth, HTTP_AUTH_TYPES, "Agent relay transport");
    const amqpAuth = parseAuthConfig(options.amqp_auth);
    assertAllowedAuthTypes(amqpAuth, BROKER_AUTH_TYPES, "Agent AMQP transport");
    const mqttAuth = parseAuthConfig(options.mqtt_auth);
    assertAllowedAuthTypes(mqttAuth, BROKER_AUTH_TYPES, "Agent MQTT transport");

    const localAmqpService = buildLocalAmqpService(agentId, options, amqpAuth);
    const localMqttService = buildLocalMqttService(agentId, options, mqttAuth);

    const bundle = readIdentity(options.storage_dir, agentId);
    let identity: AgentIdentity;
    let identityDocument: JsonMap;
    let capabilities: AgentCapabilities;
    if (!bundle) {
      if (providerIdentityKeys) {
        identity = identityFromProvider({
          agent_id: agentId,
          ...providerIdentityKeys
        });
      } else if (externalKeyProvider) {
        throw keyProviderError("Unable to load identity keys from key provider");
      } else {
        identity = createIdentity(agentId);
      }
      capabilities = new AgentCapabilities(agentId);
      identityDocument = buildIdentityDocument({
        identity,
        direct_endpoint: options.endpoint,
        relay_hints: options.relay_hints,
        trust_profile: options.trust_profile,
        capabilities: capabilities.toMap(),
        valid_days: 365,
        amqp_service: localAmqpService,
        mqtt_service: localMqttService,
        http_security_profile: options.mtls_enabled ? "mtls" : undefined,
        relay_security_profile: options.mtls_enabled ? "mtls" : undefined
      });
      applyHttpSecurityProfile(identityDocument, options.mtls_enabled);
      resignIdentityDocument(identityDocument, identity);
      writeIdentity(options.storage_dir, identity, identityDocument);
    } else {
      identity = bundle.identity;
      identityDocument = bundle.identity_document;
      if (providerIdentityKeys) {
        identity = identityFromProvider({
          agent_id: identity.agent_id,
          ...providerIdentityKeys,
          signing_kid: providerIdentityKeys.signing_kid ?? identity.signing_kid,
          encryption_kid: providerIdentityKeys.encryption_kid ?? identity.encryption_kid
        });
      } else if (externalKeyProvider) {
        throw keyProviderError("Unable to load identity keys from key provider");
      }
      capabilities = AgentCapabilities.fromMap(
        identityDocument.capabilities && typeof identityDocument.capabilities === "object"
          ? (identityDocument.capabilities as JsonMap)
          : undefined,
        agentId
      );
      const shouldRewrite =
        !verifyIdentityDocument(identityDocument) ||
        Boolean(options.endpoint) ||
        options.relay_hints.length > 0 ||
        Boolean(localAmqpService) ||
        Boolean(localMqttService);
      if (shouldRewrite) {
        const serviceRaw = identityDocument.service;
        const service =
          serviceRaw && typeof serviceRaw === "object" && !Array.isArray(serviceRaw)
            ? (serviceRaw as JsonMap)
            : {};
        const existingEndpoint = typeof service.direct_endpoint === "string" ? service.direct_endpoint : undefined;
        const existingRelayHints = Array.isArray(service.relay_hints)
          ? service.relay_hints.filter((item): item is string => typeof item === "string")
          : [];
        identityDocument = buildIdentityDocument({
          identity,
          direct_endpoint: options.endpoint ?? existingEndpoint,
          relay_hints: options.relay_hints.length > 0 ? options.relay_hints : existingRelayHints,
          trust_profile: options.trust_profile,
          capabilities: capabilities.toMap(),
          valid_days: 365,
          amqp_service: localAmqpService ?? (service.amqp as JsonMap | undefined),
          mqtt_service: localMqttService ?? (service.mqtt as JsonMap | undefined),
          http_security_profile: options.mtls_enabled ? "mtls" : undefined,
          relay_security_profile: options.mtls_enabled ? "mtls" : undefined
        });
        applyHttpSecurityProfile(identityDocument, options.mtls_enabled);
        resignIdentityDocument(identityDocument, identity);
        writeIdentity(options.storage_dir, identity, identityDocument);
      }
    }

    const effectiveRelayHints =
      options.relay_hints.length > 0
        ? options.relay_hints
        : Array.isArray((identityDocument.service as JsonMap | undefined)?.relay_hints)
          ? (((identityDocument.service as JsonMap).relay_hints as JsonValue[]) ?? []).filter(
              (item): item is string => typeof item === "string"
            )
          : [];
    const discovery = new DiscoveryClient(
      join(options.storage_dir, "discovery-cache.json"),
      options.discovery_scheme,
      effectiveRelayHints,
      options.enterprise_directory_hints,
      options.http_timeout_seconds,
      policy
    );
    discovery.seed(identityDocument);
    const transport = new TransportClient(options.http_timeout_seconds, policy);

    const amqpTransport = options.amqp_broker_url
      ? new AmqpTransportClient(
          options.amqp_broker_url,
          options.amqp_exchange,
          options.amqp_exchange_type,
          options.http_timeout_seconds,
          amqpAuth
        )
      : undefined;
    const mqttTransport = options.mqtt_broker_url
      ? new MqttTransportClient(
          options.mqtt_broker_url,
          options.mqtt_qos,
          options.mqtt_topic_prefix,
          options.http_timeout_seconds,
          30,
          mqttAuth
        )
      : undefined;

    return new AcpAgent(
      identity,
      identityDocument,
      discovery,
      transport,
      amqpTransport,
      mqttTransport,
      capabilities,
      options.storage_dir,
      options.trust_profile,
      options.relay_url,
      options.default_delivery_mode,
      keyProviderInfo,
      directTransportAuth,
      relayTransportAuth
    );
  }

  private static async resolveKeyProvider(options: AcpAgentOptions): Promise<KeyProvider> {
    if (options.key_provider === "vault") {
      if (!options.vault_url || !options.vault_path) {
        throw keyProviderError("vault_url and vault_path are required when key_provider=vault");
      }
      return new VaultKeyProvider(
        options.vault_url,
        options.vault_path,
        options.vault_token_env,
        options.vault_token,
        options.http_timeout_seconds,
        options.ca_file,
        options.allow_insecure_tls,
        options.allow_insecure_http
      );
    }
    return new LocalKeyProvider(options.storage_dir, options.cert_file, options.key_file, options.ca_file);
  }

  public agentId(): string {
    return this.identity.agent_id;
  }

  public getDeliveryStates(): Record<string, Record<string, string>> {
    const output: Record<string, Record<string, string>> = {};
    for (const [operationId, states] of this.delivery_states.entries()) {
      output[operationId] = Object.fromEntries(states.entries());
    }
    return output;
  }

  public buildWellKnownDocument(baseUrl?: string, identityDocumentUrl?: string): JsonMap {
    const resolvedBaseUrl =
      baseUrl ??
      (() => {
        const service = this.identity_document.service as JsonMap | undefined;
        const endpoint = service?.direct_endpoint;
        if (typeof endpoint !== "string" || !endpoint.trim()) {
          return undefined;
        }
        const parsed = new URL(endpoint);
        return `${parsed.protocol}//${parsed.host}`;
      })();
    if (!resolvedBaseUrl) {
      throw validationError(
        "Unable to build /.well-known/acp metadata without base_url or direct_endpoint"
      );
    }
    return buildWellKnownDocument({
      identity_document: this.identity_document,
      base_url: resolvedBaseUrl,
      identity_document_url: identityDocumentUrl,
      version: ACP_VERSION
    });
  }

  public registerIdentityDocument(identityDocument: JsonMap): void {
    this.discovery.registerIdentityDocument(identityDocument);
  }

  public async resolveWellKnown(baseUrl: string, expectedAgentId?: string): Promise<JsonMap> {
    return this.discovery.resolveWellKnown(baseUrl, expectedAgentId);
  }

  private async resolveRecipients(
    recipients: string[],
    mode: DeliveryMode
  ): Promise<{ deliverable: ResolvedRecipient[]; preflight_outcomes: DeliveryOutcome[] }> {
    const deliverable: ResolvedRecipient[] = [];
    const preflight: DeliveryOutcome[] = [];
    for (const recipient of recipients) {
      let identityDocument: JsonMap;
      try {
        identityDocument = await this.discovery.resolve(recipient);
      } catch (error) {
        preflight.push(failedOutcome(recipient, "POLICY_REJECTED", String(error)));
        continue;
      }
      const remoteCapabilities = AgentCapabilities.fromMap(
        identityDocument.capabilities && typeof identityDocument.capabilities === "object"
          ? (identityDocument.capabilities as JsonMap)
          : undefined,
        recipient
      );
      const capabilityMatch = this.capabilities.chooseCompatible(remoteCapabilities);
      if (!capabilityMatch.compatible) {
        preflight.push(
          failedOutcome(
            recipient,
            parseReasonForCapabilityMismatch(capabilityMatch.reason),
            capabilityMatch.reason ?? "No compatible capabilities"
          )
        );
        continue;
      }
      const choice = this.chooseDeliveryChannel(remoteCapabilities, identityDocument, mode);
      if (!choice.channel) {
        preflight.push(
          failedOutcome(recipient, "POLICY_REJECTED", choice.detail ?? "Delivery channel unavailable")
        );
        continue;
      }
      const publicKey =
        (((identityDocument.keys as JsonMap | undefined)?.encryption as JsonMap | undefined)
          ?.public_key as string | undefined) ?? "";
      if (!publicKey.trim()) {
        preflight.push(
          failedOutcome(recipient, "POLICY_REJECTED", "Recipient identity document missing encryption public key")
        );
        continue;
      }
      let httpAuth: AuthConfig | undefined;
      try {
        httpAuth = extractHttpAuth(identityDocument);
      } catch (error) {
        preflight.push(
          failedOutcome(recipient, "POLICY_REJECTED", `Invalid recipient HTTP auth configuration: ${String(error)}`)
        );
        continue;
      }
      deliverable.push({
        recipient,
        public_key: publicKey.trim(),
        channel: choice.channel,
        endpoint: choice.endpoint,
        http_auth: httpAuth,
        amqp_service: choice.amqp_service,
        mqtt_service: choice.mqtt_service
      });
    }
    return { deliverable, preflight_outcomes: preflight };
  }

  private chooseDeliveryChannel(
    remoteCapabilities: AgentCapabilities,
    identityDocument: JsonMap,
    mode: DeliveryMode
  ): ChannelChoice {
    const shared = this.capabilities.transports
      .map((item) => item.toLowerCase())
      .filter((transport) => remoteCapabilities.transports.map((t) => t.toLowerCase()).includes(transport));
    const serviceRaw = identityDocument.service;
    const service =
      serviceRaw && typeof serviceRaw === "object" && !Array.isArray(serviceRaw)
        ? (serviceRaw as JsonMap)
        : {};
    const directEndpoint = typeof service.direct_endpoint === "string" ? service.direct_endpoint.trim() : "";
    const hasDirect = Boolean(directEndpoint);
    const amqpService =
      service.amqp && typeof service.amqp === "object" && !Array.isArray(service.amqp)
        ? (service.amqp as JsonMap)
        : undefined;
    const mqttService =
      service.mqtt && typeof service.mqtt === "object" && !Array.isArray(service.mqtt)
        ? (service.mqtt as JsonMap)
        : undefined;
    const directAvailable = hasDirect && shared.some((t) => t === "https" || t === "http" || t === "direct");
    const relayAvailable = this.relay_url.trim().length > 0 && shared.includes("relay");
    const amqpAvailable = Boolean(amqpService) && shared.includes("amqp");
    const mqttAvailable = Boolean(mqttService) && shared.includes("mqtt");

    if (mode === "direct") {
      if (directAvailable) {
        return { channel: "direct", endpoint: directEndpoint };
      }
      return { detail: "Recipient direct endpoint is unavailable or incompatible" };
    }
    if (mode === "relay") {
      if (relayAvailable) {
        return { channel: "relay" };
      }
      return { detail: "Relay delivery is unavailable or incompatible" };
    }
    if (mode === "amqp") {
      if (amqpAvailable) {
        return { channel: "amqp", amqp_service: amqpService };
      }
      return { detail: "AMQP delivery is unavailable or incompatible" };
    }
    if (mode === "mqtt") {
      if (mqttAvailable) {
        return { channel: "mqtt", mqtt_service: mqttService };
      }
      return { detail: "MQTT delivery is unavailable or incompatible" };
    }
    if (directAvailable) {
      return { channel: "direct", endpoint: directEndpoint };
    }
    if (relayAvailable) {
      return { channel: "relay" };
    }
    if (amqpAvailable) {
      return { channel: "amqp", amqp_service: amqpService };
    }
    if (mqttAvailable) {
      return { channel: "mqtt", mqtt_service: mqttService };
    }
    return {
      detail:
        "Recipient identity document is missing direct_endpoint/amqp/mqtt and no relay fallback is compatible"
    };
  }

  private buildMessage(
    recipients: string[],
    payload: JsonMap,
    recipientPublicKeys: Record<string, string>,
    messageClass: MessageClass,
    contextId: string,
    operationId: string | undefined,
    expiresInSeconds: number,
    correlationId?: string,
    inReplyTo?: string
  ): AcpMessage {
    const envelope = buildEnvelope({
      sender: this.agentId(),
      recipients,
      message_class: messageClass,
      context_id: contextId,
      operation_id: operationId,
      expires_in_seconds: expiresInSeconds,
      correlation_id: correlationId,
      in_reply_to: inReplyTo,
      crypto_suite: DEFAULT_CRYPTO_SUITE
    });
    let protectedPayload = encryptForRecipients(payload, envelope, recipientPublicKeys);
    protectedPayload = signProtectedPayload(
      envelope,
      protectedPayload,
      this.identity.signing_private_key,
      this.identity.signing_kid
    );
    return {
      envelope,
      protected: protectedPayload,
      sender_identity_document: this.identity_document
    };
  }

  private async deliverDirect(message: AcpMessage, targets: ResolvedRecipient[]): Promise<DeliveryOutcome[]> {
    const messageMap = messageToMap(message);
    const outcomes: DeliveryOutcome[] = [];
    for (const target of targets) {
      if (!target.endpoint) {
        outcomes.push(failedOutcome(target.recipient, "POLICY_REJECTED", "Recipient direct endpoint missing"));
        continue;
      }
      try {
        const response = await this.transport.postJson(target.endpoint, messageMap, {
          protocol: "http",
          endpoint: target.endpoint,
          auth: target.http_auth ?? this.direct_transport_auth
        });
        outcomes.push(outcomeFromHttpResponse(target.recipient, response));
      } catch (error) {
        outcomes.push(
          failedOutcome(target.recipient, "POLICY_REJECTED", `Direct transport failure: ${String(error)}`)
        );
      }
    }
    return outcomes;
  }

  private async deliverRelay(message: AcpMessage, targets: ResolvedRecipient[]): Promise<DeliveryOutcome[]> {
    const outcomes: DeliveryOutcome[] = [];
    try {
      const relayResponse = await this.transport.sendToRelayWithConfig(this.relay_url, message, {
        protocol: "relay",
        endpoint: this.relay_url,
        auth: this.relay_transport_auth
      });
      const relayOutcomes =
        Array.isArray(relayResponse.outcomes) && relayResponse.outcomes.length > 0
          ? relayResponse.outcomes
          : targets.map((target) => ({ recipient: target.recipient, state: "DELIVERED" }));
      for (const relayOutcome of relayOutcomes) {
        const item =
          relayOutcome && typeof relayOutcome === "object" && !Array.isArray(relayOutcome)
            ? (relayOutcome as JsonMap)
            : {};
        outcomes.push({
          recipient: typeof item.recipient === "string" ? item.recipient : "",
          state: (typeof item.state === "string" ? item.state : "DELIVERED") as DeliveryState,
          status_code: typeof item.status_code === "number" ? item.status_code : undefined,
          response_class: parseMessageClass(item.response_class as string | undefined),
          reason_code: typeof item.reason_code === "string" ? item.reason_code : undefined,
          detail: typeof item.detail === "string" ? item.detail : undefined,
          response_message:
            item.response_message && typeof item.response_message === "object" && !Array.isArray(item.response_message)
              ? (item.response_message as JsonMap)
              : undefined
        });
      }
    } catch (error) {
      for (const target of targets) {
        outcomes.push(failedOutcome(target.recipient, "POLICY_REJECTED", `Relay transport failure: ${String(error)}`));
      }
    }
    return outcomes;
  }

  private async deliverAmqp(message: AcpMessage, target: ResolvedRecipient): Promise<DeliveryOutcome> {
    const outcome: DeliveryOutcome = { recipient: target.recipient, state: "PENDING" };
    try {
      const client = this.amqp_transport;
      if (!client && !target.amqp_service) {
        throw transportError("AMQP delivery selected but sender is not configured with an AMQP broker");
      }
      const brokerUrl = (target.amqp_service?.broker_url as string | undefined) ?? this.amqp_transport?.broker_url;
      if (!client && !brokerUrl) {
        throw transportError("AMQP delivery selected but sender is not configured with an AMQP broker");
      }
      const transportClient =
        client ??
        new AmqpTransportClient(
          brokerUrl as string,
          target.amqp_service?.exchange as string | undefined,
          undefined,
          10
        );
      await transportClient.publish(messageToMap(message), target.recipient, target.amqp_service);
      outcome.state = "DELIVERED";
    } catch (error) {
      outcome.state = "FAILED";
      outcome.reason_code = "POLICY_REJECTED";
      outcome.detail = `AMQP transport failure: ${String(error)}`;
    }
    return outcome;
  }

  private async deliverMqtt(message: AcpMessage, target: ResolvedRecipient): Promise<DeliveryOutcome> {
    const outcome: DeliveryOutcome = { recipient: target.recipient, state: "PENDING" };
    try {
      const client = this.mqtt_transport;
      if (!client && !target.mqtt_service) {
        throw transportError("MQTT delivery selected but sender is not configured with an MQTT broker");
      }
      const brokerUrl = (target.mqtt_service?.broker_url as string | undefined) ?? this.mqtt_transport?.broker_url;
      if (!client && !brokerUrl) {
        throw transportError("MQTT delivery selected but sender is not configured with an MQTT broker");
      }
      const transportClient =
        client ??
        new MqttTransportClient(
          brokerUrl as string,
          Number(target.mqtt_service?.qos ?? 1),
          this.default_delivery_mode === "mqtt" ? undefined : "acp/agent",
          10
        );
      await transportClient.publish(messageToMap(message), target.recipient, target.mqtt_service);
      outcome.state = "DELIVERED";
    } catch (error) {
      outcome.state = "FAILED";
      outcome.reason_code = "POLICY_REJECTED";
      outcome.detail = `MQTT transport failure: ${String(error)}`;
    }
    return outcome;
  }

  private syncDeliveryStates(operationId: string, outcomes: DeliveryOutcome[]): void {
    const states = new Map<string, string>();
    for (const outcome of outcomes) {
      states.set(outcome.recipient, outcome.state);
    }
    this.delivery_states.set(operationId, states);
  }

  public async send(
    recipients: string[],
    payload: JsonMap,
    context?: string,
    messageClass: MessageClass = "SEND",
    expiresInSeconds = 300,
    correlationId?: string,
    inReplyTo?: string,
    deliveryMode?: DeliveryMode
  ): Promise<SendResult> {
    if (recipients.length === 0) {
      throw validationError("send() requires at least one recipient");
    }
    const mode = deliveryMode ?? this.default_delivery_mode;
    const operationId = randomUUID();
    const contextId = context ?? `ctx:${randomUUID()}`;
    const resolved = await this.resolveRecipients(recipients, mode);
    const outcomes: DeliveryOutcome[] = [...resolved.preflight_outcomes];
    const messageIds: string[] = [];

    const directTargets = resolved.deliverable.filter((target) => target.channel === "direct");
    const relayTargets = resolved.deliverable.filter((target) => target.channel === "relay");
    const amqpTargets = resolved.deliverable.filter((target) => target.channel === "amqp");
    const mqttTargets = resolved.deliverable.filter((target) => target.channel === "mqtt");

    if (directTargets.length > 0) {
      const message = this.buildMessage(
        directTargets.map((target) => target.recipient),
        payload,
        toPublicKeyMap(directTargets),
        messageClass,
        contextId,
        operationId,
        expiresInSeconds,
        correlationId,
        inReplyTo
      );
      messageIds.push(message.envelope.message_id);
      outcomes.push(...(await this.deliverDirect(message, directTargets)));
    }
    if (relayTargets.length > 0) {
      const message = this.buildMessage(
        relayTargets.map((target) => target.recipient),
        payload,
        toPublicKeyMap(relayTargets),
        messageClass,
        contextId,
        operationId,
        expiresInSeconds,
        correlationId,
        inReplyTo
      );
      messageIds.push(message.envelope.message_id);
      outcomes.push(...(await this.deliverRelay(message, relayTargets)));
    }
    for (const target of amqpTargets) {
      const message = this.buildMessage(
        [target.recipient],
        payload,
        { [target.recipient]: target.public_key },
        messageClass,
        contextId,
        operationId,
        expiresInSeconds,
        correlationId,
        inReplyTo
      );
      messageIds.push(message.envelope.message_id);
      outcomes.push(await this.deliverAmqp(message, target));
    }
    for (const target of mqttTargets) {
      const message = this.buildMessage(
        [target.recipient],
        payload,
        { [target.recipient]: target.public_key },
        messageClass,
        contextId,
        operationId,
        expiresInSeconds,
        correlationId,
        inReplyTo
      );
      messageIds.push(message.envelope.message_id);
      outcomes.push(await this.deliverMqtt(message, target));
    }
    if (messageIds.length === 0) {
      messageIds.push(randomUUID());
    }
    const result: SendResult = {
      operation_id: operationId,
      message_id: messageIds[0],
      message_ids: messageIds,
      outcomes
    };
    this.syncDeliveryStates(operationId, outcomes);
    return result;
  }

  public async sendBasic(
    recipients: string[],
    payload: JsonMap,
    context?: string
  ): Promise<SendResult> {
    return this.send(recipients, payload, context, "SEND", 300, undefined, undefined, this.default_delivery_mode);
  }

  private async resolveSenderIdentityDocument(rawMessage: JsonMap, senderId: string): Promise<JsonMap> {
    if (
      rawMessage.sender_identity_document &&
      typeof rawMessage.sender_identity_document === "object" &&
      !Array.isArray(rawMessage.sender_identity_document)
    ) {
      const embedded = rawMessage.sender_identity_document as JsonMap;
      if (embedded.agent_id === senderId && verifyIdentityDocument(embedded)) {
        return embedded;
      }
    }
    return this.discovery.resolve(senderId);
  }

  private validateEnvelopeForInbound(envelope: Envelope): void {
    if (envelope.acp_version !== ACP_VERSION) {
      throw processingError("UNSUPPORTED_VERSION", `Unsupported ACP version: ${envelope.acp_version}`);
    }
    if (envelope.crypto_suite !== DEFAULT_CRYPTO_SUITE) {
      throw processingError("UNSUPPORTED_CRYPTO_SUITE", `Unsupported crypto suite: ${envelope.crypto_suite}`);
    }
    if (isExpired(envelope)) {
      throw processingError("EXPIRED_MESSAGE", "Message is expired");
    }
  }

  private createResponseMessage(
    senderIdentityDocument: JsonMap,
    requestEnvelope: Envelope,
    responseClass: MessageClass,
    responsePayload: JsonMap
  ): AcpMessage {
    const senderId = requestEnvelope.sender;
    const senderPublicKey =
      ((((senderIdentityDocument.keys as JsonMap).encryption as JsonMap).public_key as string | undefined) ?? "").trim();
    if (!senderPublicKey) {
      throw processingError("POLICY_REJECTED", "Sender identity document missing encryption key");
    }
    return this.buildMessage(
      [senderId],
      responsePayload,
      { [senderId]: senderPublicKey },
      responseClass,
      requestEnvelope.context_id,
      requestEnvelope.operation_id,
      300,
      requestEnvelope.correlation_id ?? requestEnvelope.operation_id,
      requestEnvelope.message_id
    );
  }

  public async decryptMessageForSelf(rawMessage: JsonMap): Promise<DecryptedMessage> {
    const message = parseAcpMessage(rawMessage);
    this.validateEnvelopeForInbound(message.envelope);
    if (!message.envelope.recipients.includes(this.agentId())) {
      throw processingError("POLICY_REJECTED", "Message is not addressed to this agent");
    }
    const senderDoc = await this.resolveSenderIdentityDocument(rawMessage, message.envelope.sender);
    const senderSigningKey =
      ((((senderDoc.keys as JsonMap).signing as JsonMap).public_key as string | undefined) ?? "").trim();
    if (!senderSigningKey) {
      throw processingError("INVALID_SIGNATURE", "Sender signing public key missing");
    }
    if (!verifyProtectedPayloadSignature(message.envelope, message.protected, senderSigningKey)) {
      throw processingError("INVALID_SIGNATURE", "Message signature verification failed");
    }
    const payload = decryptForRecipient(
      message.envelope,
      message.protected,
      this.agentId(),
      this.identity.encryption_private_key
    );
    return { message, payload };
  }

  public async receive(rawMessage: JsonMap, handler?: InboundHandler): Promise<InboundResult> {
    const result: InboundResult = {
      state: "FAILED"
    };
    let requestMessage: AcpMessage;
    try {
      requestMessage = parseAcpMessage(rawMessage);
    } catch (error) {
      result.reason_code = "POLICY_REJECTED";
      result.detail = `Invalid ACP message structure: ${String(error)}`;
      return result;
    }
    let senderDoc: JsonMap;
    try {
      this.validateEnvelopeForInbound(requestMessage.envelope);
      if (!requestMessage.envelope.recipients.includes(this.agentId())) {
        throw processingError("POLICY_REJECTED", `Recipient ${this.agentId()} not in message recipients`);
      }
      senderDoc = await this.resolveSenderIdentityDocument(rawMessage, requestMessage.envelope.sender);
      const senderSigningKey =
        ((((senderDoc.keys as JsonMap).signing as JsonMap).public_key as string | undefined) ?? "").trim();
      if (!senderSigningKey) {
        throw processingError("INVALID_SIGNATURE", "Sender signing key missing from identity document");
      }
      if (!verifyProtectedPayloadSignature(requestMessage.envelope, requestMessage.protected, senderSigningKey)) {
        throw processingError("INVALID_SIGNATURE", "Signature verification failed");
      }
      if (this.dedup.isDuplicate(requestMessage.envelope.message_id)) {
        result.state = "ACKNOWLEDGED";
        result.detail = "Duplicate message acknowledged";
        if (requestMessage.envelope.message_class !== "ACK" && requestMessage.envelope.message_class !== "FAIL") {
          result.response_message = messageToMap(
            this.createResponseMessage(
              senderDoc,
              requestMessage.envelope,
              "ACK",
              buildAckPayload(requestMessage.envelope.message_id, "duplicate")
            )
          );
        }
        return result;
      }
      const decrypted = decryptForRecipient(
        requestMessage.envelope,
        requestMessage.protected,
        this.agentId(),
        this.identity.encryption_private_key
      );
      result.decrypted_payload = decrypted;
      let responseMessage: AcpMessage | undefined;
      if (requestMessage.envelope.message_class === "CAPABILITIES") {
        responseMessage = this.createResponseMessage(
          senderDoc,
          requestMessage.envelope,
          "CAPABILITIES",
          this.capabilities.toMap()
        );
      } else if (requestMessage.envelope.message_class !== "ACK" && requestMessage.envelope.message_class !== "FAIL") {
        const ackPayload = buildAckPayload(requestMessage.envelope.message_id, "accepted");
        const handlerPayload = handler?.(decrypted, requestMessage.envelope);
        if (handlerPayload && Object.keys(handlerPayload).length > 0) {
          ackPayload.handler = handlerPayload;
        }
        responseMessage = this.createResponseMessage(senderDoc, requestMessage.envelope, "ACK", ackPayload);
      }
      this.dedup.markProcessed(requestMessage.envelope.message_id);
      result.state = "ACKNOWLEDGED";
      result.response_message = responseMessage ? messageToMap(responseMessage) : undefined;
      return result;
    } catch (error) {
      const processing = error instanceof Error ? error : new Error(String(error));
      if (error instanceof Error && "reason" in error && typeof (error as { reason?: string }).reason === "string") {
        result.reason_code = (error as { reason: string }).reason;
      } else {
        result.reason_code = "POLICY_REJECTED";
      }
      result.detail = processing.message;
      const terminal = requestMessage.envelope.message_class === "ACK" || requestMessage.envelope.message_class === "FAIL";
      if (!terminal) {
        try {
          const sender = await this.resolveSenderIdentityDocument(rawMessage, requestMessage.envelope.sender);
          result.response_message = messageToMap(
            this.createResponseMessage(
              sender,
              requestMessage.envelope,
              "FAIL",
              buildFailPayload(result.reason_code, result.detail ?? "processing error", false)
            )
          );
        } catch {
          result.response_message = undefined;
        }
      }
      return result;
    }
  }

  public async requestCapabilities(recipient: string): Promise<CapabilityRequestResult> {
    const result = await this.send(
      [recipient],
      {},
      `capabilities:${randomUUID()}`,
      "CAPABILITIES",
      300,
      undefined,
      undefined,
      this.default_delivery_mode
    );
    let capabilities: JsonMap | undefined;
    for (const outcome of result.outcomes) {
      if (!outcome.response_message) {
        continue;
      }
      try {
        const decrypted = await this.decryptMessageForSelf(outcome.response_message);
        if (decrypted.message.envelope.message_class === "CAPABILITIES") {
          capabilities = decrypted.payload;
          break;
        }
      } catch {
        continue;
      }
    }
    return { result, capabilities };
  }
}
