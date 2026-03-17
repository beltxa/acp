/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

const (
	ACPVersion               = "1.0"
	ACPIdentityVersion       = "1.0"
	DefaultCryptoSuite       = "ACP-AES256-GCM+X25519+ED25519"
	DefaultIdentityDocPath   = "/api/v1/acp/identity"
	DefaultWellKnownPath     = "/.well-known/acp"
	DefaultWellKnownCacheTTL = "public, max-age=300"
)

var SupportedTrustProfiles = map[string]struct{}{
	"self_asserted":   {},
	"domain_verified": {},
}

func IsSupportedTrustProfile(value string) bool {
	_, ok := SupportedTrustProfiles[value]
	return ok
}
