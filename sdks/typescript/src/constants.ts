export const ACP_VERSION = "1.0";
export const ACP_IDENTITY_VERSION = "1.0";
export const DEFAULT_CRYPTO_SUITE = "ACP-AES256-GCM+X25519+ED25519";
export const DEFAULT_IDENTITY_DOCUMENT_PATH = "/api/v1/acp/identity";

export const TRUST_PROFILES = ["self_asserted", "domain_verified"] as const;
export type TrustProfile = (typeof TRUST_PROFILES)[number];

export function isSupportedTrustProfile(value: string): value is TrustProfile {
  return TRUST_PROFILES.includes(value as TrustProfile);
}
