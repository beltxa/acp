package org.acp.client;

import java.util.Set;

public final class AcpConstants {
    public static final String ACP_VERSION = "1.0";
    public static final String DEFAULT_CRYPTO_SUITE = "ACP-AES256-GCM+X25519+ED25519";
    public static final String ACP_IDENTITY_VERSION = "1.0";

    public static final Set<String> TRUST_PROFILES = Set.of(
        "self_asserted",
        "domain_verified",
        "enterprise_managed",
        "regulated_assured"
    );

    private AcpConstants() {
    }
}
