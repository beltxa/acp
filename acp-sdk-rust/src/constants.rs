pub const ACP_VERSION: &str = "1.0";
pub const ACP_IDENTITY_VERSION: &str = "1.0";
pub const DEFAULT_CRYPTO_SUITE: &str = "ACP-AES256-GCM+X25519+ED25519";
pub const DEFAULT_IDENTITY_DOCUMENT_PATH: &str = "/api/v1/acp/identity";

pub const TRUST_PROFILES: &[&str] = &[
    "self_asserted",
    "domain_verified",
    "enterprise_managed",
    "regulated_assured",
];

pub fn is_supported_trust_profile(profile: &str) -> bool {
    TRUST_PROFILES.iter().any(|item| *item == profile)
}
