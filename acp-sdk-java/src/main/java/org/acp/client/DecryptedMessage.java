package org.acp.client;

import java.util.Map;

public record DecryptedMessage(AcpMessage message, Map<String, Object> payload) {
}
