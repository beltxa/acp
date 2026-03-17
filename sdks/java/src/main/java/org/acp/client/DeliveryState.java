/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

public enum DeliveryState {
    PENDING,
    DELIVERED,
    ACKNOWLEDGED,
    FAILED,
    DECLINED,
    EXPIRED
}
