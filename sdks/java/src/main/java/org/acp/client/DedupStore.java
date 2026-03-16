package org.acp.client;

import java.time.Duration;
import java.time.Instant;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class DedupStore {
    private final Duration ttl;
    private final Map<String, Instant> processed = new ConcurrentHashMap<>();

    public DedupStore(Duration ttl) {
        this.ttl = ttl == null ? Duration.ofHours(1) : ttl;
    }

    public boolean isDuplicate(String messageId) {
        cleanupExpired();
        return processed.containsKey(messageId);
    }

    public void markProcessed(String messageId) {
        processed.put(messageId, Instant.now());
    }

    private void cleanupExpired() {
        Instant cutoff = Instant.now().minus(ttl);
        Iterator<Map.Entry<String, Instant>> iterator = processed.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<String, Instant> item = iterator.next();
            if (item.getValue().isBefore(cutoff)) {
                iterator.remove();
            }
        }
    }
}
