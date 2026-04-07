/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package org.acp.client;

import java.util.LinkedHashMap;
import java.util.Map;

public class AuthConfig {
    private String type = "none";
    private Map<String, String> parameters = new LinkedHashMap<>();

    public AuthConfig() {
    }

    public AuthConfig(String type, Map<String, String> parameters) {
        this.type = type == null ? "none" : type;
        setParameters(parameters);
    }

    public String getType() {
        return type;
    }

    public AuthConfig setType(String type) {
        this.type = type == null ? "none" : type;
        return this;
    }

    public Map<String, String> getParameters() {
        return parameters;
    }

    public AuthConfig setParameters(Map<String, String> parameters) {
        this.parameters = parameters == null ? new LinkedHashMap<>() : new LinkedHashMap<>(parameters);
        return this;
    }
}
