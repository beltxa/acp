/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.core.json.JsonWriteFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.util.Map;

public final class JsonSupport {
    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
        .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
        .enable(JsonWriteFeature.ESCAPE_NON_ASCII)
        .build();

    private JsonSupport() {
    }

    public static ObjectMapper mapper() {
        return OBJECT_MAPPER;
    }

    public static String toJson(Object value) {
        try {
            return OBJECT_MAPPER.writeValueAsString(value);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to serialize JSON", exc);
        }
    }

    public static byte[] utf8Bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static <T> T fromJson(String value, Class<T> type) {
        try {
            return OBJECT_MAPPER.readValue(value, type);
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to parse JSON", exc);
        }
    }

    public static Map<String, Object> mapFromJson(String value) {
        try {
            return OBJECT_MAPPER.readValue(value, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception exc) {
            throw new IllegalStateException("Unable to parse JSON object", exc);
        }
    }

    public static Map<String, Object> toMap(Object value) {
        return OBJECT_MAPPER.convertValue(value, new TypeReference<Map<String, Object>>() {
        });
    }

    public static <T> T convert(Object value, Class<T> type) {
        return OBJECT_MAPPER.convertValue(value, type);
    }
}
