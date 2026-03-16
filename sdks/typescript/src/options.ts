import { JsonMap } from "./jsonSupport";
import { DeliveryMode } from "./messages";

export interface AcpAgentOptions {
  storage_dir: string;
  endpoint?: string;
  relay_url: string;
  relay_hints: string[];
  enterprise_directory_hints: string[];
  discovery_scheme: string;
  trust_profile: string;
  default_delivery_mode: DeliveryMode;
  http_timeout_seconds: number;
  allow_insecure_http: boolean;
  allow_insecure_tls: boolean;
  mtls_enabled: boolean;
  ca_file?: string;
  cert_file?: string;
  key_file?: string;
  key_provider: "local" | "vault";
  vault_url?: string;
  vault_path?: string;
  vault_token_env: string;
  vault_token?: string;
  amqp_broker_url?: string;
  amqp_exchange: string;
  amqp_exchange_type: string;
  mqtt_broker_url?: string;
  mqtt_qos: number;
  mqtt_topic_prefix: string;
  extra: JsonMap;
}

export function defaultAgentOptions(): AcpAgentOptions {
  return {
    storage_dir: ".acp-data",
    relay_url: "https://localhost:8080",
    relay_hints: [],
    enterprise_directory_hints: [],
    discovery_scheme: "https",
    trust_profile: "self_asserted",
    default_delivery_mode: "auto",
    http_timeout_seconds: 10,
    allow_insecure_http: false,
    allow_insecure_tls: false,
    mtls_enabled: false,
    key_provider: "local",
    vault_token_env: "VAULT_TOKEN",
    amqp_exchange: "acp.exchange",
    amqp_exchange_type: "direct",
    mqtt_qos: 1,
    mqtt_topic_prefix: "acp/agent",
    extra: {}
  };
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  return fallback;
}

function asString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

export function optionsFromConfigMap(config: JsonMap | undefined): AcpAgentOptions {
  const options = defaultAgentOptions();
  if (!config) {
    return options;
  }
  options.allow_insecure_http = asBoolean(config.allow_insecure_http, false);
  options.allow_insecure_tls = asBoolean(config.allow_insecure_tls, false);
  options.mtls_enabled = asBoolean(config.mtls_enabled, false);
  options.ca_file = asString(config.ca_file);
  options.cert_file = asString(config.cert_file);
  options.key_file = asString(config.key_file);
  options.key_provider = (asString(config.key_provider) as "local" | "vault") ?? "local";
  options.vault_url = asString(config.vault_url);
  options.vault_path = asString(config.vault_path);
  options.vault_token_env = asString(config.vault_token_env) ?? "VAULT_TOKEN";
  options.endpoint = asString(config.endpoint);
  options.relay_url = asString(config.relay_url) ?? options.relay_url;
  options.discovery_scheme = asString(config.discovery_scheme) ?? options.discovery_scheme;
  options.storage_dir = asString(config.storage_dir) ?? options.storage_dir;
  options.vault_token = asString(config.vault_token);
  options.amqp_broker_url = asString(config.amqp_broker_url);
  options.amqp_exchange = asString(config.amqp_exchange) ?? options.amqp_exchange;
  options.amqp_exchange_type = asString(config.amqp_exchange_type) ?? options.amqp_exchange_type;
  options.mqtt_broker_url = asString(config.mqtt_broker_url);
  options.mqtt_topic_prefix = asString(config.mqtt_topic_prefix) ?? options.mqtt_topic_prefix;
  options.mqtt_qos = Math.min(2, Math.max(0, asNumber(config.mqtt_qos) ?? options.mqtt_qos));
  if (Array.isArray(config.relay_hints)) {
    options.relay_hints = config.relay_hints.filter((item): item is string => typeof item === "string");
  }
  if (Array.isArray(config.enterprise_directory_hints)) {
    options.enterprise_directory_hints = config.enterprise_directory_hints.filter(
      (item): item is string => typeof item === "string"
    );
  }
  return options;
}

export function optionsToConfigMap(options: AcpAgentOptions): JsonMap {
  return {
    allow_insecure_http: options.allow_insecure_http,
    allow_insecure_tls: options.allow_insecure_tls,
    mtls_enabled: options.mtls_enabled,
    ca_file: options.ca_file ?? null,
    cert_file: options.cert_file ?? null,
    key_file: options.key_file ?? null,
    key_provider: options.key_provider,
    vault_url: options.vault_url ?? null,
    vault_path: options.vault_path ?? null,
    vault_token_env: options.vault_token_env
  };
}
