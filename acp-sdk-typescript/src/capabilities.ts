import { ACP_VERSION, DEFAULT_CRYPTO_SUITE } from "./constants.js";
import { JsonMap } from "./jsonSupport.js";

export interface CapabilityMatch {
  compatible: boolean;
  reason?: string;
}

export class AgentCapabilities {
  public agent_id: string;
  public protocol_versions: string[];
  public crypto_suites: string[];
  public transports: string[];
  public supports: Record<string, boolean>;

  public constructor(agentId: string) {
    this.agent_id = agentId;
    this.protocol_versions = [ACP_VERSION];
    this.crypto_suites = [DEFAULT_CRYPTO_SUITE];
    this.transports = ["https", "http", "relay", "amqp", "mqtt"];
    this.supports = {
      capabilities: true,
      compensate: true,
      amqp: true,
      mqtt: true,
      overlay: true
    };
  }

  public toMap(): JsonMap {
    return {
      agent_id: this.agent_id,
      protocol_versions: [...this.protocol_versions],
      crypto_suites: [...this.crypto_suites],
      transports: [...this.transports],
      supports: { ...this.supports }
    };
  }

  public static fromMap(map: JsonMap | undefined, fallbackAgentId: string): AgentCapabilities {
    const capabilities = new AgentCapabilities(fallbackAgentId);
    if (!map) {
      return capabilities;
    }
    const agentId = typeof map.agent_id === "string" ? map.agent_id : fallbackAgentId;
    capabilities.agent_id = agentId;
    if (Array.isArray(map.protocol_versions)) {
      capabilities.protocol_versions = map.protocol_versions
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
    }
    if (Array.isArray(map.crypto_suites)) {
      capabilities.crypto_suites = map.crypto_suites
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
    }
    if (Array.isArray(map.transports)) {
      capabilities.transports = map.transports
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim().toLowerCase())
        .filter((item) => item.length > 0);
    }
    if (map.supports && typeof map.supports === "object" && !Array.isArray(map.supports)) {
      const supports: Record<string, boolean> = {};
      for (const [key, value] of Object.entries(map.supports)) {
        supports[key] = Boolean(value);
      }
      capabilities.supports = supports;
    }
    return capabilities;
  }

  public chooseCompatible(remote: AgentCapabilities): CapabilityMatch {
    if (!this.protocol_versions.some((version) => remote.protocol_versions.includes(version))) {
      return { compatible: false, reason: "No compatible protocol version" };
    }
    if (!this.crypto_suites.some((suite) => remote.crypto_suites.includes(suite))) {
      return { compatible: false, reason: "No compatible crypto suite" };
    }
    if (!this.transports.some((transport) => remote.transports.includes(transport))) {
      return { compatible: false, reason: "No compatible transport" };
    }
    return { compatible: true };
  }
}
