package org.acp.client.framework;

import org.acp.client.AcpAgent;
import org.acp.client.DeliveryMode;
import org.acp.client.FailReason;
import org.acp.client.OverlayInboundAdapter;
import org.acp.client.OverlayOutboundAdapter;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class OverlayHttpRuntime {
    private final AcpAgent agent;
    private final String baseUrl;
    private final OverlayInboundAdapter inboundAdapter;
    private final OverlayOutboundAdapter outboundAdapter;

    public OverlayHttpRuntime(
        AcpAgent agent,
        String baseUrl,
        Function<Map<String, Object>, Map<String, Object>> businessHandler
    ) {
        this(agent, baseUrl, businessHandler, null);
    }

    public OverlayHttpRuntime(
        AcpAgent agent,
        String baseUrl,
        Function<Map<String, Object>, Map<String, Object>> businessHandler,
        Function<Map<String, Object>, Map<String, Object>> passthroughHandler
    ) {
        this.agent = agent;
        this.baseUrl = normalizeBaseUrl(baseUrl);
        this.inboundAdapter = new OverlayInboundAdapter(agent, businessHandler, passthroughHandler);
        this.outboundAdapter = new OverlayOutboundAdapter(agent);
    }

    @SuppressWarnings("unchecked")
    public HttpOverlayResponse handleMessageBody(Object body) {
        if (!(body instanceof Map<?, ?> raw)) {
            return invalidRequest("Expected JSON object request body");
        }
        try {
            Map<String, Object> response = inboundAdapter.handleRequest((Map<String, Object>) raw);
            return new HttpOverlayResponse(200, response);
        } catch (IllegalArgumentException exc) {
            return invalidRequest(exc.getMessage());
        }
    }

    public Map<String, Object> wellKnownDocument() {
        return agent.buildWellKnownDocument(baseUrl);
    }

    public Map<String, Object> identityDocumentPayload() {
        return Map.of("identity_document", agent.getIdentityDocument());
    }

    public Map<String, Object> sendBusinessPayload(
        Map<String, Object> payload,
        String targetBaseUrl,
        String recipientAgentId,
        String context,
        DeliveryMode deliveryMode,
        int expiresInSeconds
    ) {
        OverlayOutboundAdapter.OverlaySendResult sendResult = outboundAdapter.sendBusinessPayload(
            payload,
            targetBaseUrl,
            recipientAgentId,
            context,
            deliveryMode,
            expiresInSeconds
        );
        Map<String, Object> result = new LinkedHashMap<>();
        OverlayOutboundAdapter.OverlayTarget target = sendResult.target();
        if (target != null) {
            Map<String, Object> targetMap = new LinkedHashMap<>();
            targetMap.put("agent_id", target.agentId());
            targetMap.put("base_url", target.baseUrl());
            targetMap.put("well_known_url", target.wellKnownUrl());
            targetMap.put("identity_document_url", target.identityDocumentUrl());
            result.put("target", targetMap);
        } else {
            result.put("target", null);
        }
        result.put("send_result", sendResult.sendResult().toMap());
        return result;
    }

    private static HttpOverlayResponse invalidRequest(String detail) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("mode", "invalid");
        body.put("state", "FAILED");
        body.put("reason_code", FailReason.POLICY_REJECTED.name());
        body.put("detail", detail);
        body.put("response_message", null);
        return new HttpOverlayResponse(
            400,
            body
        );
    }

    private static String normalizeBaseUrl(String baseUrl) {
        if (isBlank(baseUrl)) {
            throw new IllegalArgumentException("baseUrl is required");
        }
        return baseUrl.trim().replaceAll("/+$", "");
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    public record HttpOverlayResponse(
        int statusCode,
        Map<String, Object> body
    ) {
    }
}
