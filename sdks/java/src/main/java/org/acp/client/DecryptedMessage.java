/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.Map;

public record DecryptedMessage(AcpMessage message, Map<String, Object> payload) {
}
