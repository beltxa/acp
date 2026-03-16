package org.acp.client;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DedupStoreTest {
    @Test
    void tracksDuplicatesByMessageId() {
        DedupStore store = new DedupStore(Duration.ofMinutes(5));
        String messageId = "msg-1";

        assertFalse(store.isDuplicate(messageId));
        store.markProcessed(messageId);
        assertTrue(store.isDuplicate(messageId));
    }
}
