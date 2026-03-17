/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class OverlayInboundAdapter {
    private final AcpAgent agent;
    private final Function<Map<String, Object>, Map<String, Object>> businessHandler;
    private final Function<Map<String, Object>, Map<String, Object>> passthroughHandler;

    public OverlayInboundAdapter(
        AcpAgent agent,
        Function<Map<String, Object>, Map<String, Object>> businessHandler
    ) {
        this(agent, businessHandler, null);
    }

    public OverlayInboundAdapter(
        AcpAgent agent,
        Function<Map<String, Object>, Map<String, Object>> businessHandler,
        Function<Map<String, Object>, Map<String, Object>> passthroughHandler
    ) {
        this.agent = agent;
        this.businessHandler = businessHandler;
        this.passthroughHandler = passthroughHandler;
    }

    public static boolean isAcpHttpMessage(Map<String, Object> requestBody) {
        if (requestBody == null) {
            return false;
        }
        return requestBody.get("envelope") instanceof Map<?, ?>
            && requestBody.get("protected") instanceof Map<?, ?>;
    }

    public Map<String, Object> handleRequest(Map<String, Object> requestBody) {
        if (requestBody == null) {
            throw new IllegalArgumentException("Overlay inbound adapter requires a JSON object request body");
        }
        if (!isAcpHttpMessage(requestBody)) {
            if (passthroughHandler == null) {
                throw new IllegalArgumentException(
                    "Request is not an ACP message and no passthroughHandler is configured"
                );
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("mode", "passthrough");
            result.put("payload", passthroughHandler.apply(requestBody));
            return result;
        }
        InboundResult inbound = agent.receive(
            requestBody,
            (payload, envelope) -> businessHandler.apply(payload)
        );
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", "acp");
        Map<String, Object> inboundMap = JsonSupport.toMap(inbound);
        result.put("acp_result", inboundMap);
        result.put("state", inboundMap.get("state"));
        result.put("reason_code", inboundMap.get("reason_code"));
        result.put("detail", inboundMap.get("detail"));
        result.put("response_message", inboundMap.get("response_message"));
        return result;
    }
}
