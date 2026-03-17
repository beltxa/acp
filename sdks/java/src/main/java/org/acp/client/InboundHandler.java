/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.Map;

@FunctionalInterface
public interface InboundHandler {
    Map<String, Object> handle(Map<String, Object> payload, Envelope envelope);
}
