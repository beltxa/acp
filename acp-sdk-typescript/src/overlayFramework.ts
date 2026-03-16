import { AcpAgent } from "./agent.js";
import { AcpError } from "./errors.js";
import { JsonMap, JsonValue, toJsonMap } from "./jsonSupport.js";
import { DeliveryMode } from "./messages.js";
import {
  BusinessHandler,
  OverlayInboundAdapter,
  OverlayOutboundAdapter,
  PassthroughHandler,
  invalidOverlayRequest
} from "./overlay.js";

export const WELL_KNOWN_CACHE_CONTROL = "public, max-age=300";

export interface OverlayHttpResponse {
  status_code: number;
  body: JsonMap;
}

export interface OverlayConfig {
  agent: AcpAgent;
  base_url: string;
  passthrough_handler?: PassthroughHandler;
}

function sendResultToMap(result: JsonMap): JsonMap {
  const output: JsonMap = {};
  const target =
    result.target && typeof result.target === "object" && !Array.isArray(result.target)
      ? (result.target as JsonMap)
      : undefined;
  output.target = target ?? null;
  output.send_result =
    result.send_result && typeof result.send_result === "object" && !Array.isArray(result.send_result)
      ? (result.send_result as JsonMap)
      : null;
  return output;
}

export class OverlayFrameworkRuntime {
  public readonly inbound_adapter: OverlayInboundAdapter;
  public readonly outbound_adapter: OverlayOutboundAdapter;

  public constructor(
    public readonly agent: AcpAgent,
    public readonly base_url: string,
    businessHandler: BusinessHandler,
    passthroughHandler?: PassthroughHandler
  ) {
    if (!base_url.trim()) {
      throw new AcpError("VALIDATION", "base_url is required");
    }
    this.base_url = base_url.replace(/\/+$/, "");
    this.inbound_adapter = new OverlayInboundAdapter(agent, businessHandler, passthroughHandler);
    this.outbound_adapter = new OverlayOutboundAdapter(agent);
  }

  public static create(
    agent: AcpAgent,
    baseUrl: string,
    businessHandler: BusinessHandler,
    passthroughHandler?: PassthroughHandler
  ): OverlayFrameworkRuntime {
    return new OverlayFrameworkRuntime(agent, baseUrl, businessHandler, passthroughHandler);
  }

  public async handleMessageBody(body: JsonValue): Promise<OverlayHttpResponse> {
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return {
        status_code: 400,
        body: invalidOverlayRequest("Expected JSON object request body")
      };
    }
    try {
      const response = await this.inbound_adapter.handleRequest(toJsonMap(body));
      return { status_code: 200, body: response };
    } catch (error) {
      return {
        status_code: 400,
        body: invalidOverlayRequest(String(error))
      };
    }
  }

  public wellKnownDocument(): JsonMap {
    return this.agent.buildWellKnownDocument(this.base_url);
  }

  public static wellKnownHeaders(): JsonMap {
    return {
      "Cache-Control": WELL_KNOWN_CACHE_CONTROL
    };
  }

  public identityDocumentPayload(): JsonMap {
    return {
      identity_document: this.agent.identity_document
    };
  }

  public async sendBusinessPayload(input: {
    payload: JsonMap;
    target_base_url?: string;
    recipient_agent_id?: string;
    context?: string;
    delivery_mode?: DeliveryMode;
    expires_in_seconds?: number;
  }): Promise<JsonMap> {
    const result = await this.outbound_adapter.sendBusinessPayload(input);
    return sendResultToMap(result as unknown as JsonMap);
  }

  public async sendAcp(
    targetUrl: string,
    payload: JsonMap,
    recipientAgentId?: string,
    context?: string,
    deliveryMode: DeliveryMode = "auto",
    expiresInSeconds = 300
  ): Promise<JsonMap> {
    return this.sendBusinessPayload({
      payload,
      target_base_url: targetUrl,
      recipient_agent_id: recipientAgentId,
      context,
      delivery_mode: deliveryMode,
      expires_in_seconds: expiresInSeconds
    });
  }

  public static async handle(
    requestBody: JsonValue,
    businessHandler: BusinessHandler,
    config: OverlayConfig
  ): Promise<OverlayHttpResponse> {
    try {
      const runtime = new OverlayFrameworkRuntime(
        config.agent,
        config.base_url,
        businessHandler,
        config.passthrough_handler
      );
      return runtime.handleMessageBody(requestBody);
    } catch (error) {
      return {
        status_code: 400,
        body: invalidOverlayRequest(String(error))
      };
    }
  }
}

export class OverlayClient {
  public readonly outbound_adapter: OverlayOutboundAdapter;

  public constructor(public readonly agent: AcpAgent) {
    this.outbound_adapter = new OverlayOutboundAdapter(agent);
  }

  public static create(agent: AcpAgent): OverlayClient {
    return new OverlayClient(agent);
  }

  public async sendAcp(
    targetUrl: string,
    payload: JsonMap,
    recipientAgentId?: string,
    context?: string,
    deliveryMode: DeliveryMode = "auto",
    expiresInSeconds = 300
  ): Promise<JsonMap> {
    const result = await this.outbound_adapter.sendBusinessPayload({
      payload,
      target_base_url: targetUrl,
      recipient_agent_id: recipientAgentId,
      context,
      delivery_mode: deliveryMode,
      expires_in_seconds: expiresInSeconds
    });
    return sendResultToMap(result as unknown as JsonMap);
  }
}

export function acpOverlayInbound(
  agent: AcpAgent,
  handler: BusinessHandler,
  passthrough = false
): (payload: JsonMap) => Promise<JsonMap> {
  let currentAgent = agent;
  const passthroughHandler: PassthroughHandler | undefined = passthrough ? handler : undefined;
  return async (payload: JsonMap): Promise<JsonMap> => {
    const inbound = new OverlayInboundAdapter(currentAgent, handler, passthroughHandler);
    const response = await inbound.handleRequest(payload);
    currentAgent = inbound.agent;
    return response;
  };
}
