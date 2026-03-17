/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class CanonicalJson {
    private CanonicalJson() {
    }

    public static String stringify(Object value) {
        Object normalized = normalize(value);
        return JsonSupport.toJson(normalized);
    }

    public static byte[] bytes(Object value) {
        return JsonSupport.utf8Bytes(stringify(value));
    }

    @SuppressWarnings("unchecked")
    private static Object normalize(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Map<?, ?> rawMap) {
            TreeMap<String, Object> sorted = new TreeMap<>();
            for (Map.Entry<?, ?> entry : rawMap.entrySet()) {
                sorted.put(String.valueOf(entry.getKey()), normalize(entry.getValue()));
            }
            return sorted;
        }
        if (value instanceof List<?> rawList) {
            List<Object> normalizedList = new ArrayList<>(rawList.size());
            for (Object item : rawList) {
                normalizedList.add(normalize(item));
            }
            return normalizedList;
        }
        if (value instanceof CharSequence
            || value instanceof Number
            || value instanceof Boolean) {
            return value;
        }
        Map<String, Object> asMap = JsonSupport.mapper().convertValue(value, Map.class);
        return normalize(asMap);
    }
}
