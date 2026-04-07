/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import mqtt, { IClientOptions, MqttClient } from "mqtt";
import { readFileSync } from "node:fs";
import { JsonMap, JsonValue } from "./jsonSupport.js";
import { invalidArgument, transportError, validationError } from "./errors.js";
import {
  AuthConfig,
  AuthType,
  assertAllowedAuthTypes,
  authParameter,
  parseAuthConfig,
  parseAuthFromService,
  serializeAuthConfig
} from "./transportAuth.js";

export const DEFAULT_MQTT_QOS = 1;
export const DEFAULT_MQTT_TOPIC_PREFIX = "acp/agent";

export type MqttMessageHandler = (message: JsonMap) => boolean | Promise<boolean>;
const MQTT_AUTH_TYPES: ReadonlySet<AuthType> = new Set(["none", "username_password", "mtls", "custom"]);

function toQos(qos: number): 0 | 1 | 2 {
  if (qos <= 0) {
    return 0;
  }
  if (qos >= 2) {
    return 2;
  }
  return 1;
}

function clampQos(qos: number): number {
  return Math.min(2, Math.max(0, qos));
}

function pickString(service: JsonMap | undefined, key: string, fallback: string): string {
  const value = service?.[key];
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function valueAsNumber(value: JsonValue | undefined): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

export function metadataProperties(message: JsonMap): Record<string, string> {
  const envelope =
    message.envelope && typeof message.envelope === "object" && !Array.isArray(message.envelope)
      ? (message.envelope as JsonMap)
      : {};
  const metadata: Record<string, string> = {};
  for (const [source, destination] of [
    ["acp_version", "acp_version"],
    ["message_class", "acp_message_class"],
    ["message_id", "acp_message_id"],
    ["operation_id", "acp_operation_id"],
    ["sender", "acp_sender"]
  ]) {
    const value = envelope[source];
    if (typeof value === "string" && value.trim()) {
      metadata[destination] = value.trim();
    }
  }
  return metadata;
}

export class MqttTransportClient {
  public readonly broker_url: string;
  public readonly qos: number;
  public readonly topic_prefix: string;
  public readonly timeout_seconds: number;
  public readonly keepalive_seconds: number;
  public readonly auth: AuthConfig | undefined;

  public constructor(
    brokerUrl: string,
    qos = DEFAULT_MQTT_QOS,
    topicPrefix = DEFAULT_MQTT_TOPIC_PREFIX,
    timeoutSeconds = 10,
    keepaliveSeconds = 30,
    auth?: unknown
  ) {
    if (!brokerUrl.trim()) {
      throw invalidArgument("broker_url must be provided");
    }
    this.broker_url = brokerUrl.trim();
    this.qos = clampQos(qos);
    this.topic_prefix = topicPrefix.trim().replace(/\/+$/, "") || DEFAULT_MQTT_TOPIC_PREFIX;
    this.timeout_seconds = Math.max(1, timeoutSeconds);
    this.keepalive_seconds = Math.max(5, keepaliveSeconds);
    this.auth = parseAuthConfig(auth);
    assertAllowedAuthTypes(this.auth, MQTT_AUTH_TYPES, "MQTT transport");
  }

  public static agentIdentifierToken(agentId: string): string {
    const match = /^agent:(?<name>[^@]+)(?:@(?<domain>.+))?$/.exec(agentId);
    if (!match?.groups?.name) {
      throw validationError(`Invalid agent identifier: ${agentId}`);
    }
    const base = match.groups.domain ? `${match.groups.name}.${match.groups.domain}` : match.groups.name;
    const normalized = base
      .split("")
      .map((char) => (/^[A-Za-z0-9._-]$/.test(char) ? char : "."))
      .join("")
      .split(".")
      .filter((segment) => segment.length > 0)
      .join(".")
      .toLowerCase();
    return normalized || "unknown";
  }

  public static topicForAgent(agentId: string, topicPrefix = DEFAULT_MQTT_TOPIC_PREFIX): string {
    return `${topicPrefix.replace(/\/+$/, "")}/${MqttTransportClient.agentIdentifierToken(agentId)}`;
  }

  public static buildServiceHint(
    agentId: string,
    brokerUrl: string,
    topic?: string,
    qos = DEFAULT_MQTT_QOS,
    topicPrefix = DEFAULT_MQTT_TOPIC_PREFIX,
    auth?: unknown
  ): JsonMap {
    const hint: JsonMap = {
      broker_url: brokerUrl,
      topic: topic?.trim() || MqttTransportClient.topicForAgent(agentId, topicPrefix),
      qos: clampQos(qos)
    };
    const parsedAuth = parseAuthConfig(auth);
    assertAllowedAuthTypes(parsedAuth, MQTT_AUTH_TYPES, "MQTT transport");
    const serialized = serializeAuthConfig(parsedAuth);
    if (serialized) {
      hint.auth = serialized;
    }
    return hint;
  }

  private connectClient(
    brokerUrl: string,
    auth: AuthConfig | undefined
  ): Promise<MqttClient> {
    const options: IClientOptions = {
      protocolVersion: 5,
      keepalive: this.keepalive_seconds,
      reconnectPeriod: 0,
      connectTimeout: this.timeout_seconds * 1000
    };
    const parsed = new URL(brokerUrl);
    if (parsed.username) {
      options.username = decodeURIComponent(parsed.username);
      options.password = decodeURIComponent(parsed.password);
    }
    if (auth && auth.type !== "none") {
      if (auth.type === "username_password") {
        options.username = authParameter(auth, "username", "MQTT username_password auth");
        options.password = authParameter(auth, "password", "MQTT username_password auth");
      } else if (auth.type === "custom") {
        if (auth.parameters.username?.trim()) {
          options.username = auth.parameters.username.trim();
          options.password = (auth.parameters.password ?? "").trim();
        }
      }
      if (auth.type === "mtls") {
        options.cert = readFileSync(authParameter(auth, "cert_path", "MQTT mTLS auth"));
        options.key = readFileSync(authParameter(auth, "key_path", "MQTT mTLS auth"));
        if (auth.parameters.ca_path?.trim()) {
          options.ca = readFileSync(auth.parameters.ca_path.trim());
        }
      } else if (
        auth.type === "custom" &&
        auth.parameters.cert_path?.trim() &&
        auth.parameters.key_path?.trim()
      ) {
        options.cert = readFileSync(auth.parameters.cert_path.trim());
        options.key = readFileSync(auth.parameters.key_path.trim());
        if (auth.parameters.ca_path?.trim()) {
          options.ca = readFileSync(auth.parameters.ca_path.trim());
        }
      }
    }
    return new Promise((resolve, reject) => {
      const client = mqtt.connect(brokerUrl, options);
      const onConnect = (): void => {
        cleanup();
        resolve(client);
      };
      const onError = (error: Error): void => {
        cleanup();
        client.end(true);
        reject(error);
      };
      const cleanup = (): void => {
        client.off("connect", onConnect);
        client.off("error", onError);
      };
      client.once("connect", onConnect);
      client.once("error", onError);
    });
  }

  public async publish(message: JsonMap, recipientAgentId: string, service?: JsonMap): Promise<void> {
    const brokerUrl = pickString(service, "broker_url", this.broker_url);
    const auth = parseAuthFromService(service) ?? this.auth;
    assertAllowedAuthTypes(auth, MQTT_AUTH_TYPES, "MQTT transport");
    const topic = pickString(
      service,
      "topic",
      MqttTransportClient.topicForAgent(recipientAgentId, this.topic_prefix)
    );
    const qos = clampQos(valueAsNumber(service?.qos) ?? this.qos);
    const properties = metadataProperties(message);
    const client = await this.connectClient(brokerUrl, auth);
    try {
      await new Promise<void>((resolve, reject) => {
        client.publish(
          topic,
          JSON.stringify(message),
          {
            qos: toQos(qos),
            properties: {
              userProperties: properties
            }
          },
          (error?: Error) => {
            if (error) {
              reject(error);
              return;
            }
            resolve();
          }
        );
      });
    } catch (error) {
      throw transportError(`mqtt publish failed: ${String(error)}`);
    } finally {
      client.end(true);
    }
  }

  public async consume(
    agentId: string,
    handler: MqttMessageHandler,
    service?: JsonMap,
    maxMessages = 0,
    pollTimeoutMs = 1000
  ): Promise<number> {
    const brokerUrl = pickString(service, "broker_url", this.broker_url);
    const auth = parseAuthFromService(service) ?? this.auth;
    assertAllowedAuthTypes(auth, MQTT_AUTH_TYPES, "MQTT transport");
    const topic = pickString(service, "topic", MqttTransportClient.topicForAgent(agentId, this.topic_prefix));
    const qos = clampQos(valueAsNumber(service?.qos) ?? this.qos);
    const limit = maxMessages === 0 ? Number.MAX_SAFE_INTEGER : maxMessages;
    const client = await this.connectClient(brokerUrl, auth);
    let processed = 0;
    try {
      await new Promise<void>((resolve, reject) => {
        client.subscribe(topic, { qos: toQos(qos) }, (error: Error | null) => {
          if (error instanceof Error) {
            reject(error);
            return;
          }
          resolve();
        });
      });
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          cleanup();
          resolve();
        }, pollTimeoutMs);
        const cleanup = (): void => {
          clearTimeout(timeout);
          client.off("message", onMessage);
        };
        const onMessage = async (_topic: string, payload: Buffer): Promise<void> => {
          if (processed >= limit) {
            cleanup();
            resolve();
            return;
          }
          try {
            const parsed = JSON.parse(payload.toString("utf-8")) as JsonValue;
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
              await handler(parsed as JsonMap);
            }
          } catch {
            // Keep behavior tolerant: invalid messages are ignored.
          }
          processed += 1;
          if (processed >= limit) {
            cleanup();
            resolve();
          }
        };
        client.on("message", onMessage);
      });
      return processed;
    } catch (error) {
      throw transportError(`mqtt consume failed: ${String(error)}`);
    } finally {
      client.end(true);
    }
  }
}
