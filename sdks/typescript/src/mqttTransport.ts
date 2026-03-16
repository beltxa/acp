import mqtt, { IClientOptions, MqttClient } from "mqtt";
import { JsonMap, JsonValue } from "./jsonSupport";
import { invalidArgument, transportError, validationError } from "./errors";

export const DEFAULT_MQTT_QOS = 1;
export const DEFAULT_MQTT_TOPIC_PREFIX = "acp/agent";

export type MqttMessageHandler = (message: JsonMap) => boolean | Promise<boolean>;

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

  public constructor(
    brokerUrl: string,
    qos = DEFAULT_MQTT_QOS,
    topicPrefix = DEFAULT_MQTT_TOPIC_PREFIX,
    timeoutSeconds = 10,
    keepaliveSeconds = 30
  ) {
    if (!brokerUrl.trim()) {
      throw invalidArgument("broker_url must be provided");
    }
    this.broker_url = brokerUrl.trim();
    this.qos = clampQos(qos);
    this.topic_prefix = topicPrefix.trim().replace(/\/+$/, "") || DEFAULT_MQTT_TOPIC_PREFIX;
    this.timeout_seconds = Math.max(1, timeoutSeconds);
    this.keepalive_seconds = Math.max(5, keepaliveSeconds);
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
    topicPrefix = DEFAULT_MQTT_TOPIC_PREFIX
  ): JsonMap {
    return {
      broker_url: brokerUrl,
      topic: topic?.trim() || MqttTransportClient.topicForAgent(agentId, topicPrefix),
      qos: clampQos(qos)
    };
  }

  private connectClient(brokerUrl: string): Promise<MqttClient> {
    const options: IClientOptions = {
      protocolVersion: 5,
      keepalive: this.keepalive_seconds,
      reconnectPeriod: 0,
      connectTimeout: this.timeout_seconds * 1000
    };
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
    const topic = pickString(
      service,
      "topic",
      MqttTransportClient.topicForAgent(recipientAgentId, this.topic_prefix)
    );
    const qos = clampQos(valueAsNumber(service?.qos) ?? this.qos);
    const properties = metadataProperties(message);
    const client = await this.connectClient(brokerUrl);
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
    const topic = pickString(service, "topic", MqttTransportClient.topicForAgent(agentId, this.topic_prefix));
    const qos = clampQos(valueAsNumber(service?.qos) ?? this.qos);
    const limit = maxMessages === 0 ? Number.MAX_SAFE_INTEGER : maxMessages;
    const client = await this.connectClient(brokerUrl);
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
