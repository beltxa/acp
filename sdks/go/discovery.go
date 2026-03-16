package acp

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type cachedDocument struct {
	IdentityDocument map[string]any `json:"identity_document"`
	FetchedAt        string         `json:"fetched_at"`
}

func cacheValid(identityDocument map[string]any) bool {
	validUntilRaw, ok := identityDocument["valid_until"].(string)
	if !ok {
		return false
	}
	validUntil, err := time.Parse(time.RFC3339, validUntilRaw)
	if err != nil {
		return false
	}
	return validUntil.After(time.Now().UTC())
}

func extractIdentityDocument(body map[string]any) map[string]any {
	if nested, ok := body["identity_document"].(map[string]any); ok {
		return nested
	}
	if _, hasAgent := body["agent_id"]; hasAgent {
		if _, hasKeys := body["keys"]; hasKeys {
			if _, hasService := body["service"]; hasService {
				return body
			}
		}
	}
	return nil
}

type DiscoveryClient struct {
	cachePath      string
	defaultScheme  string
	relayHints     []string
	directoryHints []string
	timeoutSeconds int
	policy         HTTPSecurityPolicy
	httpClient     *http.Client

	lock     sync.Mutex
	cache    map[string]cachedDocument
	registry map[string]map[string]any
}

func NewDiscoveryClient(
	cachePath string,
	defaultScheme string,
	relayHints []string,
	directoryHints []string,
	timeoutSeconds int,
	policy HTTPSecurityPolicy,
) (*DiscoveryClient, error) {
	httpClient, err := BuildHTTPClient(policy, timeoutSeconds)
	if err != nil {
		return nil, err
	}
	client := &DiscoveryClient{
		cachePath:      strings.TrimSpace(cachePath),
		defaultScheme:  firstNonBlankString(strings.TrimSpace(defaultScheme), "https"),
		relayHints:     append([]string{}, relayHints...),
		directoryHints: append([]string{}, directoryHints...),
		timeoutSeconds: maxInt(timeoutSeconds, 1),
		policy:         policy,
		httpClient:     httpClient,
		cache:          map[string]cachedDocument{},
		registry:       map[string]map[string]any{},
	}
	client.loadCache()
	return client, nil
}

func (client *DiscoveryClient) Seed(identityDocument map[string]any) {
	agentID, ok := identityDocument["agent_id"].(string)
	if !ok || strings.TrimSpace(agentID) == "" {
		return
	}
	client.lock.Lock()
	client.cache[agentID] = cachedDocument{
		IdentityDocument: identityDocument,
		FetchedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	client.lock.Unlock()
	client.persistCache()
}

func (client *DiscoveryClient) RegisterIdentityDocument(identityDocument map[string]any) error {
	agentID, ok := identityDocument["agent_id"].(string)
	if !ok || strings.TrimSpace(agentID) == "" {
		return ValidationError("Identity document missing agent_id")
	}
	client.lock.Lock()
	client.registry[agentID] = identityDocument
	client.cache[agentID] = cachedDocument{
		IdentityDocument: identityDocument,
		FetchedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	client.lock.Unlock()
	client.persistCache()
	return nil
}

func (client *DiscoveryClient) Resolve(agentID string) (map[string]any, error) {
	client.lock.Lock()
	if registered, ok := client.registry[agentID]; ok {
		client.lock.Unlock()
		return registered, nil
	}
	client.lock.Unlock()
	if cached := client.tryCache(agentID); cached != nil {
		return cached, nil
	}
	if wellKnown := client.tryWellKnown(agentID); wellKnown != nil {
		client.cacheIdentity(agentID, wellKnown)
		return wellKnown, nil
	}
	if relayLookup := client.tryHintLookups(client.relayHints, agentID); relayLookup != nil {
		client.cacheIdentity(agentID, relayLookup)
		return relayLookup, nil
	}
	if directoryLookup := client.tryHintLookups(client.directoryHints, agentID); directoryLookup != nil {
		client.cacheIdentity(agentID, directoryLookup)
		return directoryLookup, nil
	}
	return nil, DiscoveryError(fmt.Sprintf("Unable to resolve identity document for %s", agentID))
}

func (client *DiscoveryClient) ResolveWellKnown(baseURL string, expectedAgentID string) (map[string]any, error) {
	wellKnownURL, err := WellKnownURLFromBase(baseURL)
	if err != nil {
		return nil, err
	}
	resolved := client.resolveWellKnownURL(wellKnownURL, expectedAgentID)
	if resolved == nil {
		return nil, DiscoveryError(fmt.Sprintf("Unable to resolve well-known metadata from %s", wellKnownURL))
	}
	identityDocument, _ := resolved["identity_document"].(map[string]any)
	agentID, _ := identityDocument["agent_id"].(string)
	if strings.TrimSpace(agentID) == "" {
		return nil, DiscoveryError("Well-known discovery returned identity document without agent_id")
	}
	client.cacheIdentity(agentID, identityDocument)
	resolved["well_known_url"] = wellKnownURL
	return resolved, nil
}

func (client *DiscoveryClient) tryCache(agentID string) map[string]any {
	client.lock.Lock()
	cached, ok := client.cache[agentID]
	client.lock.Unlock()
	if !ok {
		return nil
	}
	if cacheValid(cached.IdentityDocument) {
		return cached.IdentityDocument
	}
	client.lock.Lock()
	delete(client.cache, agentID)
	client.lock.Unlock()
	client.persistCache()
	return nil
}

func (client *DiscoveryClient) tryWellKnown(agentID string) map[string]any {
	parts, err := ParseAgentID(agentID)
	if err != nil || strings.TrimSpace(parts.Domain) == "" {
		return nil
	}
	wellKnownURL := fmt.Sprintf("%s://%s/.well-known/acp", client.defaultScheme, parts.Domain)
	resolved := client.resolveWellKnownURL(wellKnownURL, agentID)
	if resolved == nil {
		return nil
	}
	identityDocument, _ := resolved["identity_document"].(map[string]any)
	return identityDocument
}

func (client *DiscoveryClient) tryHintLookups(hints []string, agentID string) map[string]any {
	for _, hint := range hints {
		endpoint := strings.TrimRight(hint, "/") + "/discover"
		body := client.fetchJSON(endpoint, map[string]string{"agent_id": agentID}, "Discovery hint lookup")
		if body == nil {
			continue
		}
		identityDocument := extractIdentityDocument(body)
		if identityDocument != nil && VerifyIdentityDocument(identityDocument) {
			return identityDocument
		}
	}
	return nil
}

func (client *DiscoveryClient) resolveWellKnownURL(wellKnownURL string, expectedAgentID string) map[string]any {
	body := client.fetchJSON(wellKnownURL, nil, "Discovery .well-known lookup")
	if body == nil {
		return nil
	}
	wellKnown, err := ParseWellKnownDocument(body)
	if err != nil {
		return nil
	}
	if expectedAgentID != "" {
		if agentID, _ := wellKnown["agent_id"].(string); agentID != expectedAgentID {
			return nil
		}
	}
	identityReference, err := ResolveIdentityDocumentReference(wellKnown, wellKnownURL)
	if err != nil {
		return nil
	}
	identityBody := client.fetchJSON(identityReference, nil, "Discovery identity document lookup")
	if identityBody == nil {
		return nil
	}
	identityDocument := extractIdentityDocument(identityBody)
	if identityDocument == nil || !VerifyIdentityDocument(identityDocument) {
		return nil
	}
	if expectedAgentID != "" {
		if agentID, _ := identityDocument["agent_id"].(string); agentID != expectedAgentID {
			return nil
		}
	}
	return map[string]any{
		"well_known":        wellKnown,
		"identity_document": identityDocument,
	}
}

func (client *DiscoveryClient) fetchJSON(rawURL string, query map[string]string, context string) map[string]any {
	parsed, err := ValidateHTTPURL(rawURL, client.policy.AllowInsecureHTTP, client.policy.MTLSEnabled, context)
	if err != nil {
		return nil
	}
	if len(query) > 0 {
		values := parsed.Query()
		for key, value := range query {
			values.Set(key, value)
		}
		parsed.RawQuery = values.Encode()
	}
	request, err := http.NewRequest(http.MethodGet, parsed.String(), nil)
	if err != nil {
		return nil
	}
	response, err := client.httpClient.Do(request)
	if err != nil {
		return nil
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil
	}
	rawBody, err := io.ReadAll(response.Body)
	if err != nil {
		return nil
	}
	parsedBody, err := ParseJSONMap(rawBody)
	if err != nil {
		return nil
	}
	return parsedBody
}

func (client *DiscoveryClient) cacheIdentity(agentID string, identityDocument map[string]any) {
	client.lock.Lock()
	client.cache[agentID] = cachedDocument{
		IdentityDocument: identityDocument,
		FetchedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	client.lock.Unlock()
	client.persistCache()
}

func (client *DiscoveryClient) loadCache() {
	if client.cachePath == "" {
		return
	}
	raw, err := os.ReadFile(client.cachePath)
	if err != nil {
		return
	}
	parsed := map[string]cachedDocument{}
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return
	}
	client.lock.Lock()
	for agentID, entry := range parsed {
		if entry.IdentityDocument != nil {
			client.cache[agentID] = entry
		}
	}
	client.lock.Unlock()
}

func (client *DiscoveryClient) persistCache() {
	if client.cachePath == "" {
		return
	}
	client.lock.Lock()
	snapshot := map[string]cachedDocument{}
	for key, value := range client.cache {
		snapshot[key] = value
	}
	client.lock.Unlock()
	data, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return
	}
	_ = os.MkdirAll(filepath.Dir(client.cachePath), 0o755)
	_ = os.WriteFile(client.cachePath, data, 0o644)
}

func withQuery(rawURL string, query map[string]string) string {
	if len(query) == 0 {
		return rawURL
	}
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	values := parsed.Query()
	for key, value := range query {
		values.Set(key, value)
	}
	parsed.RawQuery = values.Encode()
	return parsed.String()
}
