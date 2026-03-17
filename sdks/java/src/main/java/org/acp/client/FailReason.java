/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

public enum FailReason {
    UNSUPPORTED_VERSION,
    UNSUPPORTED_CRYPTO_SUITE,
    UNSUPPORTED_MESSAGE_CLASS,
    INVALID_SIGNATURE,
    EXPIRED_MESSAGE,
    POLICY_REJECTED,
    PAYLOAD_TOO_LARGE,
    UNSUPPORTED_PROFILE
}
