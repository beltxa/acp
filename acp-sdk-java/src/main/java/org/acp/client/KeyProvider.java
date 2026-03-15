package org.acp.client;

import java.util.Map;

public interface KeyProvider {
    IdentityKeyMaterial loadIdentityKeys(String agentId);

    TlsMaterial loadTlsMaterial(String agentId);

    String loadCaBundle(String agentId);

    Map<String, Object> describe();
}
