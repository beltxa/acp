/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.List;
import java.util.Map;

public class OverlayOutboundAdapter {
    private final AcpAgent agent;

    public OverlayOutboundAdapter(AcpAgent agent) {
        this.agent = agent;
    }

    public OverlayTarget resolveTarget(String targetBaseUrl, String expectedAgentId) {
        Map<String, Object> resolved = agent.resolveWellKnown(targetBaseUrl, expectedAgentId);
        @SuppressWarnings("unchecked")
        Map<String, Object> wellKnown = (Map<String, Object>) resolved.get("well_known");
        @SuppressWarnings("unchecked")
        Map<String, Object> identityDocument = (Map<String, Object>) resolved.get("identity_document");

        String agentId = identityDocument == null ? null : asString(identityDocument.get("agent_id"));
        if (isBlank(agentId)) {
            throw new IllegalStateException("Resolved well-known metadata missing identity_document.agent_id");
        }
        String wellKnownUrl = asString(resolved.get("well_known_url"));
        String identityDocumentUrl = wellKnown == null ? null : asString(wellKnown.get("identity_document"));
        if (isBlank(identityDocumentUrl)) {
            throw new IllegalStateException("Resolved well-known metadata missing identity_document URL");
        }
        return new OverlayTarget(
            agentId,
            targetBaseUrl == null ? null : targetBaseUrl.replaceAll("/+$", ""),
            wellKnownUrl,
            identityDocumentUrl
        );
    }

    public OverlaySendResult sendBusinessPayload(
        Map<String, Object> payload,
        String targetBaseUrl,
        String recipientAgentId,
        String context,
        DeliveryMode deliveryMode,
        int expiresInSeconds
    ) {
        OverlayTarget resolvedTarget = null;
        String resolvedRecipient = recipientAgentId;
        if (!isBlank(targetBaseUrl)) {
            resolvedTarget = resolveTarget(targetBaseUrl, recipientAgentId);
            if (isBlank(resolvedRecipient)) {
                resolvedRecipient = resolvedTarget.agentId();
            }
        }
        if (isBlank(resolvedRecipient)) {
            throw new IllegalArgumentException(
                "sendBusinessPayload requires recipientAgentId or targetBaseUrl for well-known bootstrap"
            );
        }
        SendResult sendResult = agent.send(
            List.of(resolvedRecipient),
            payload,
            context,
            MessageClass.SEND,
            expiresInSeconds,
            null,
            null,
            deliveryMode == null ? DeliveryMode.AUTO : deliveryMode
        );
        return new OverlaySendResult(resolvedTarget, sendResult);
    }

    private static String asString(Object value) {
        return value instanceof String str ? str : null;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    public record OverlayTarget(
        String agentId,
        String baseUrl,
        String wellKnownUrl,
        String identityDocumentUrl
    ) {
    }

    public record OverlaySendResult(
        OverlayTarget target,
        SendResult sendResult
    ) {
    }
}
