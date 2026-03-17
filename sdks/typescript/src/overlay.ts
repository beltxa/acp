/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

import { AcpAgent } from "./agent";
import { JsonMap, JsonValue, toJsonMap } from "./jsonSupport";
import { DeliveryMode } from "./messages";
import { validationError } from "./errors";

export interface OverlayTarget {
  agent_id: string;
  base_url: string;
  well_known_url: string;
  identity_document_url: string;
}

export interface OverlaySendResult {
  target?: OverlayTarget;
  send_result: JsonMap;
}

export type BusinessHandler = (payload: JsonMap) => JsonMap | undefined;
export type PassthroughHandler = (payload: JsonMap) => JsonMap | undefined;

export function isAcpHttpMessage(body: JsonMap): boolean {
  return Boolean(
    body.envelope &&
      typeof body.envelope === "object" &&
      !Array.isArray(body.envelope) &&
      body.protected &&
      typeof body.protected === "object" &&
      !Array.isArray(body.protected)
  );
}

export function invalidOverlayRequest(detail: string): JsonMap {
  return {
    mode: "invalid",
    state: "FAILED",
    reason_code: "POLICY_REJECTED",
    detail,
    response_message: null
  };
}

export class OverlayInboundAdapter {
  public constructor(
    public agent: AcpAgent,
    private readonly businessHandler: BusinessHandler,
    private readonly passthroughHandler?: PassthroughHandler
  ) {}

  public async handleRequest(body: JsonMap): Promise<JsonMap> {
    if (!isAcpHttpMessage(body)) {
      if (this.passthroughHandler) {
        return {
          mode: "passthrough",
          payload: this.passthroughHandler(body) ?? {}
        };
      }
      throw validationError("Request is not an ACP message and no passthrough_handler is configured");
    }
    const inbound = await this.agent.receive(body, (payload) => this.businessHandler(payload));
    return {
      mode: "acp",
      acp_result: inbound as unknown as JsonValue,
      state: inbound.state,
      reason_code: inbound.reason_code ?? null,
      detail: inbound.detail ?? null,
      response_message: inbound.response_message ?? null
    };
  }
}

export class OverlayOutboundAdapter {
  public constructor(public agent: AcpAgent) {}

  public async resolveTarget(targetBaseUrl: string, expectedAgentId?: string): Promise<OverlayTarget> {
    const resolved = await this.agent.resolveWellKnown(targetBaseUrl, expectedAgentId);
    const wellKnown = toJsonMap(resolved.well_known);
    const identityDocument = toJsonMap(resolved.identity_document);
    const agentId = identityDocument.agent_id;
    if (typeof agentId !== "string" || !agentId.trim()) {
      throw validationError(
        "Resolved well-known metadata did not include a valid identity_document.agent_id"
      );
    }
    const identityDocumentUrl = wellKnown.identity_document;
    if (typeof identityDocumentUrl !== "string" || !identityDocumentUrl.trim()) {
      throw validationError("Resolved well-known metadata did not include a valid identity_document URL");
    }
    return {
      agent_id: agentId,
      base_url: targetBaseUrl.replace(/\/+$/, ""),
      well_known_url: typeof resolved.well_known_url === "string" ? resolved.well_known_url : "",
      identity_document_url: identityDocumentUrl
    };
  }

  public async sendBusinessPayload(input: {
    payload: JsonMap;
    target_base_url?: string;
    recipient_agent_id?: string;
    context?: string;
    delivery_mode?: DeliveryMode;
    expires_in_seconds?: number;
  }): Promise<OverlaySendResult> {
    let target: OverlayTarget | undefined;
    let recipientAgentId = input.recipient_agent_id;
    if (input.target_base_url) {
      target = await this.resolveTarget(input.target_base_url, recipientAgentId);
      recipientAgentId = recipientAgentId ?? target.agent_id;
    }
    if (!recipientAgentId) {
      throw validationError(
        "send_business_payload requires recipient_agent_id or target_base_url for well-known bootstrap"
      );
    }
    const sendResult = await this.agent.send(
      [recipientAgentId],
      input.payload,
      input.context,
      "SEND",
      input.expires_in_seconds ?? 300,
      undefined,
      undefined,
      input.delivery_mode
    );
    return {
      target,
      send_result: sendResult as unknown as JsonMap
    };
  }
}
