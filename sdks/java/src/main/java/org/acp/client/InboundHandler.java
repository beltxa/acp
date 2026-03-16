package org.acp.client;

import java.util.Map;

@FunctionalInterface
public interface InboundHandler {
    Map<String, Object> handle(Map<String, Object> payload, Envelope envelope);
}
