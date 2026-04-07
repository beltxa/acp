/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { connect } from "amqplib";
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

export const DEFAULT_AMQP_EXCHANGE = "acp.exchange";
export const DEFAULT_AMQP_EXCHANGE_TYPE = "direct";

export type AmqpMessageHandler = (message: JsonMap) => boolean | Promise<boolean>;
const AMQP_AUTH_TYPES: ReadonlySet<AuthType> = new Set(["none", "username_password", "mtls", "custom"]);

function pickString(service: JsonMap | undefined, key: string, fallback: string): string {
  const value = service?.[key];
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function metadataHeaders(message: JsonMap): Record<string, string> {
  const envelope =
    message.envelope && typeof message.envelope === "object" && !Array.isArray(message.envelope)
      ? (message.envelope as JsonMap)
      : {};
  const headers: Record<string, string> = {};
  for (const [source, destination] of [
    ["acp_version", "acp_version"],
    ["message_class", "acp_message_class"],
    ["message_id", "acp_message_id"],
    ["operation_id", "acp_operation_id"],
    ["sender", "acp_sender"]
  ]) {
    const value = envelope[source];
    if (typeof value === "string" && value.trim()) {
      headers[destination] = value.trim();
    }
  }
  return headers;
}

export class AmqpTransportClient {
  public readonly broker_url: string;
  public readonly exchange: string;
  public readonly exchange_type: string;
  public readonly timeout_seconds: number;
  public readonly auth: AuthConfig | undefined;

  public constructor(
    brokerUrl: string,
    exchange?: string,
    exchangeType?: string,
    timeoutSeconds = 10,
    auth?: unknown
  ) {
    if (!brokerUrl.trim()) {
      throw invalidArgument("broker_url must be provided");
    }
    this.broker_url = brokerUrl;
    this.exchange = exchange?.trim() || DEFAULT_AMQP_EXCHANGE;
    this.exchange_type = exchangeType?.trim() || DEFAULT_AMQP_EXCHANGE_TYPE;
    this.timeout_seconds = Math.max(1, timeoutSeconds);
    this.auth = parseAuthConfig(auth);
    assertAllowedAuthTypes(this.auth, AMQP_AUTH_TYPES, "AMQP transport");
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
      .join(".");
    return normalized || "unknown";
  }

  public static queueNameForAgent(agentId: string): string {
    return `acp.agent.${AmqpTransportClient.agentIdentifierToken(agentId)}`;
  }

  public static routingKeyForAgent(agentId: string): string {
    return `agent.${AmqpTransportClient.agentIdentifierToken(agentId)}`;
  }

  public static buildServiceHint(
    agentId: string,
    brokerUrl: string,
    exchange?: string,
    auth?: unknown
  ): JsonMap {
    const hint: JsonMap = {
      broker_url: brokerUrl,
      exchange: exchange?.trim() || DEFAULT_AMQP_EXCHANGE,
      queue: AmqpTransportClient.queueNameForAgent(agentId),
      routing_key: AmqpTransportClient.routingKeyForAgent(agentId)
    };
    const parsedAuth = parseAuthConfig(auth);
    assertAllowedAuthTypes(parsedAuth, AMQP_AUTH_TYPES, "AMQP transport");
    const serialized = serializeAuthConfig(parsedAuth);
    if (serialized) {
      hint.auth = serialized;
    }
    return hint;
  }

  public async publish(message: JsonMap, recipientAgentId: string, service?: JsonMap): Promise<void> {
    const brokerUrl = pickString(service, "broker_url", this.broker_url);
    const auth = parseAuthFromService(service) ?? this.auth;
    assertAllowedAuthTypes(auth, AMQP_AUTH_TYPES, "AMQP transport");
    const connectionAuth = this.resolveConnectionAuth(brokerUrl, auth);
    const exchange = pickString(service, "exchange", this.exchange);
    const queue = pickString(service, "queue", AmqpTransportClient.queueNameForAgent(recipientAgentId));
    const routingKey = pickString(
      service,
      "routing_key",
      AmqpTransportClient.routingKeyForAgent(recipientAgentId)
    );
    const body = JSON.stringify(message);
    const headers = metadataHeaders(message);
    let connection;
    let channel;
    try {
      connection = await connect(connectionAuth.brokerUrl, connectionAuth.socketOptions);
      channel = await connection.createChannel();
      await channel.assertExchange(exchange, this.exchange_type, { durable: true });
      await channel.assertQueue(queue, { durable: true });
      await channel.bindQueue(queue, exchange, routingKey);
      channel.publish(exchange, routingKey, Buffer.from(body, "utf-8"), {
        contentType: "application/json",
        deliveryMode: 2,
        headers
      });
      await channel.close();
      await connection.close();
    } catch (error) {
      if (channel) {
        await channel.close().catch(() => undefined);
      }
      if (connection) {
        await connection.close().catch(() => undefined);
      }
      throw transportError(`amqp publish failed: ${String(error)}`);
    }
  }

  public async consume(
    agentId: string,
    handler: AmqpMessageHandler,
    service?: JsonMap,
    maxMessages = 0
  ): Promise<number> {
    const brokerUrl = pickString(service, "broker_url", this.broker_url);
    const auth = parseAuthFromService(service) ?? this.auth;
    assertAllowedAuthTypes(auth, AMQP_AUTH_TYPES, "AMQP transport");
    const connectionAuth = this.resolveConnectionAuth(brokerUrl, auth);
    const exchange = pickString(service, "exchange", this.exchange);
    const queue = pickString(service, "queue", AmqpTransportClient.queueNameForAgent(agentId));
    const routingKey = pickString(service, "routing_key", AmqpTransportClient.routingKeyForAgent(agentId));
    const limit = maxMessages === 0 ? Number.MAX_SAFE_INTEGER : maxMessages;
    let processed = 0;
    let connection;
    let channel;
    try {
      connection = await connect(connectionAuth.brokerUrl, connectionAuth.socketOptions);
      channel = await connection.createChannel();
      await channel.assertExchange(exchange, this.exchange_type, { durable: true });
      await channel.assertQueue(queue, { durable: true });
      await channel.bindQueue(queue, exchange, routingKey);
      while (processed < limit) {
        const result = await channel.get(queue, { noAck: false });
        if (!result) {
          break;
        }
        let shouldAck = false;
        try {
          const parsed = JSON.parse(result.content.toString("utf-8")) as JsonValue;
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            shouldAck = await handler(parsed as JsonMap);
          }
        } catch {
          shouldAck = false;
        }
        if (shouldAck) {
          channel.ack(result);
        } else {
          channel.nack(result, false, true);
        }
        processed += 1;
      }
      await channel.close();
      await connection.close();
      return processed;
    } catch (error) {
      if (channel) {
        await channel.close().catch(() => undefined);
      }
      if (connection) {
        await connection.close().catch(() => undefined);
      }
      throw transportError(`amqp consume failed: ${String(error)}`);
    }
  }

  private resolveConnectionAuth(
    brokerUrl: string,
    auth: AuthConfig | undefined
  ): { brokerUrl: string; socketOptions: Record<string, unknown> | undefined } {
    if (!auth || auth.type === "none") {
      return { brokerUrl, socketOptions: undefined };
    }
    const parsed = new URL(brokerUrl);
    const socketOptions: Record<string, unknown> = {};

    if (auth.type === "username_password" || auth.type === "custom") {
      const username = auth.parameters.username;
      const password = auth.parameters.password;
      if (auth.type === "username_password") {
        parsed.username = authParameter(auth, "username", "AMQP username_password auth");
        parsed.password = authParameter(auth, "password", "AMQP username_password auth");
      } else if (typeof username === "string" && username.trim()) {
        parsed.username = username.trim();
        parsed.password = (password ?? "").trim();
      }
    }

    if (auth.type === "mtls" || auth.type === "custom") {
      const certPath = auth.parameters.cert_path;
      const keyPath = auth.parameters.key_path;
      const caPath = auth.parameters.ca_path;
      if (auth.type === "mtls") {
        const cert = readFileSync(authParameter(auth, "cert_path", "AMQP mTLS auth"));
        const key = readFileSync(authParameter(auth, "key_path", "AMQP mTLS auth"));
        socketOptions.cert = cert;
        socketOptions.key = key;
        if (caPath && caPath.trim()) {
          socketOptions.ca = [readFileSync(caPath.trim())];
        }
      } else if (typeof certPath === "string" && certPath.trim() && typeof keyPath === "string" && keyPath.trim()) {
        socketOptions.cert = readFileSync(certPath.trim());
        socketOptions.key = readFileSync(keyPath.trim());
        if (typeof caPath === "string" && caPath.trim()) {
          socketOptions.ca = [readFileSync(caPath.trim())];
        }
      }
    }

    return {
      brokerUrl: parsed.toString(),
      socketOptions: Object.keys(socketOptions).length > 0 ? socketOptions : undefined
    };
  }
}
