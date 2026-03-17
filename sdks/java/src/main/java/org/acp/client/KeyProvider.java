/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.Map;

public interface KeyProvider {
    IdentityKeyMaterial loadIdentityKeys(String agentId);

    TlsMaterial loadTlsMaterial(String agentId);

    String loadCaBundle(String agentId);

    Map<String, Object> describe();
}
