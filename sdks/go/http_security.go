/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

package acp

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type HTTPSecurityPolicy struct {
	AllowInsecureHTTP bool
	AllowInsecureTLS  bool
	MTLSEnabled       bool
	CAFile            string
	CertFile          string
	KeyFile           string
}

func normalizeOptionalPath(value string) (string, error) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return "", nil
	}
	stats, err := os.Stat(trimmed)
	if err != nil || !stats.Mode().IsRegular() {
		return "", ValidationError(fmt.Sprintf("configured file does not exist or is not a file: %s", trimmed))
	}
	return trimmed, nil
}

func ValidateHTTPURL(rawURL string, allowInsecureHTTP bool, mtlsEnabled bool, context string) (*url.URL, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil, ValidationError(fmt.Sprintf("%s has invalid URL: %v", context, err))
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, ValidationError(fmt.Sprintf("%s requires an http(s) URL, got: %s", context, rawURL))
	}
	if strings.TrimSpace(parsed.Hostname()) == "" {
		return nil, ValidationError(fmt.Sprintf("%s URL is missing host: %s", context, rawURL))
	}
	if parsed.Scheme == "http" && mtlsEnabled {
		return nil, ValidationError(fmt.Sprintf("%s cannot use HTTP (%s) when mtls_enabled=true. Use https:// endpoints.", context, rawURL))
	}
	if parsed.Scheme == "http" && !allowInsecureHTTP {
		return nil, ValidationError(fmt.Sprintf("%s uses insecure HTTP (%s). Set allow_insecure_http=true only for local/dev/demo workflows.", context, rawURL))
	}
	return parsed, nil
}

func ValidateHTTPClientPolicy(policy HTTPSecurityPolicy, context string) error {
	certFile, err := normalizeOptionalPath(policy.CertFile)
	if err != nil {
		return err
	}
	keyFile, err := normalizeOptionalPath(policy.KeyFile)
	if err != nil {
		return err
	}
	if _, err := normalizeOptionalPath(policy.CAFile); err != nil {
		return err
	}
	if policy.MTLSEnabled {
		if certFile == "" {
			return ValidationError(fmt.Sprintf("%s requires cert_file when mtls_enabled=true", context))
		}
		if keyFile == "" {
			return ValidationError(fmt.Sprintf("%s requires key_file when mtls_enabled=true", context))
		}
	} else if (certFile == "") != (keyFile == "") {
		return ValidationError(fmt.Sprintf("%s requires both cert_file and key_file when either is configured", context))
	}
	return nil
}

func BuildHTTPClient(policy HTTPSecurityPolicy, timeoutSeconds int) (*http.Client, error) {
	if err := ValidateHTTPClientPolicy(policy, "HTTP client configuration"); err != nil {
		return nil, err
	}
	tlsConfig := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: policy.AllowInsecureTLS,
	}
	if strings.TrimSpace(policy.CAFile) != "" {
		data, err := os.ReadFile(strings.TrimSpace(policy.CAFile))
		if err != nil {
			return nil, ValidationError(fmt.Sprintf("unable to read ca_file: %v", err))
		}
		pool := x509.NewCertPool()
		if ok := pool.AppendCertsFromPEM(data); !ok {
			return nil, ValidationError("unable to parse CA bundle from ca_file")
		}
		tlsConfig.RootCAs = pool
	}
	if strings.TrimSpace(policy.CertFile) != "" || strings.TrimSpace(policy.KeyFile) != "" {
		cert, err := tls.LoadX509KeyPair(strings.TrimSpace(policy.CertFile), strings.TrimSpace(policy.KeyFile))
		if err != nil {
			return nil, ValidationError(fmt.Sprintf("unable to load client certificate: %v", err))
		}
		tlsConfig.Certificates = []tls.Certificate{cert}
	}
	transport := &http.Transport{
		TLSClientConfig: tlsConfig,
	}
	return &http.Client{
		Transport: transport,
		Timeout:   time.Duration(maxInt(timeoutSeconds, 1)) * time.Second,
	}, nil
}

func WarnIfInsecureHTTPUsed(endpoint string, context string) {
	if strings.HasPrefix(strings.TrimSpace(strings.ToLower(endpoint)), "http://") {
		log.Printf("%s is using insecure HTTP (%s) because allow_insecure_http=true", context, endpoint)
	}
}
