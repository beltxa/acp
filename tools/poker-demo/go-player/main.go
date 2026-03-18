package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	acp "github.com/beltxa/acp/sdks/go"
)

const (
	pokerProfile       = "UCW_POKER_V1"
	openAIResponsesURL = "https://api.openai.com/v1/responses"
)

var legalActions = map[string]struct{}{
	"FOLD":  {},
	"CHECK": {},
	"CALL":  {},
	"BET":   {},
	"RAISE": {},
}

type config struct {
	ServerPort           int
	PlayerID             string
	EntityID             string
	Personality          string
	LLMProvider          string
	Model                string
	LocalAgentID         string
	DealerAgentID        string
	PublicBaseURL        string
	AcpMessagePath       string
	AcpStorageDir        string
	AcpDiscoveryScheme   string
	AcpRelayURL          string
	AcpAllowInsecureHTTP bool
	AcpAllowInsecureTLS  bool
	AcpAllowInvalidSig   bool
	AcpCAFile            string
	AcpDeliveryMode      acp.DeliveryMode
	ActionTimeoutMillis  int
	OpenAIAPIKey         string
}

type personality struct {
	Type             string
	BluffFrequency   float64
	AggressionFactor float64
	StrategyHint     string
}

type decisionEngine struct {
	cfg  config
	http *http.Client
}

type runtime struct {
	cfg      config
	agent    *acp.AcpAgent
	decision *decisionEngine

	mu             sync.Mutex
	sequence       int
	eliminated     bool
	activeTableID  string
	lastHandNumber int
	holeCards      []string
}

type inboundEvent struct {
	Type       string
	TableID    string
	HandNumber *int
	Payload    map[string]any
}

func main() {
	cfg := loadConfig()
	agent, err := buildAgent(cfg)
	if err != nil {
		log.Fatalf("unable to initialize ACP agent: %v", err)
	}

	rt := &runtime{
		cfg:      cfg,
		agent:    agent,
		decision: newDecisionEngine(cfg),
	}

	log.Printf(
		"Player %s (%s) started with provider=%s model=%s personality=%s localAgentId=%s",
		cfg.PlayerID,
		cfg.EntityID,
		cfg.LLMProvider,
		cfg.Model,
		cfg.Personality,
		cfg.LocalAgentID,
	)

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/acp/messages", rt.handleACPMessage)
	mux.HandleFunc("/.well-known/acp", rt.handleWellKnown)
	mux.HandleFunc("/api/v1/acp/identity", rt.handleIdentity)

	addr := fmt.Sprintf("0.0.0.0:%d", cfg.ServerPort)
	log.Printf("Go poker player listening on %s", addr)
	if err := http.ListenAndServe(addr, logRequests(mux)); err != nil {
		log.Fatalf("server stopped: %v", err)
	}
}

func logRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		log.Printf("%s HTTP %s %s from %s", request.Method, request.URL.Path, request.Proto, request.RemoteAddr)
		next.ServeHTTP(writer, request)
	})
}

func loadConfig() config {
	return config{
		ServerPort:           intEnv("SERVER_PORT", 8091),
		PlayerID:             env("POKER_PLAYER_PLAYER_ID", "Player-1"),
		EntityID:             env("POKER_PLAYER_ENTITY_ID", "Entity-A"),
		Personality:          env("POKER_PLAYER_PERSONALITY", "TIGHT_AGGRESSIVE"),
		LLMProvider:          env("POKER_PLAYER_LLM_PROVIDER", "openai"),
		Model:                env("POKER_PLAYER_MODEL", "chatgpt-5.2-instant"),
		LocalAgentID:         env("POKER_PLAYER_LOCAL_AGENT_ID", "agent:player1@localhost:8091"),
		DealerAgentID:        env("POKER_PLAYER_DEALER_AGENT_ID", "agent:dealer@localhost:8090"),
		PublicBaseURL:        env("POKER_PLAYER_PUBLIC_BASE_URL", "http://localhost:8091"),
		AcpMessagePath:       env("POKER_PLAYER_ACP_MESSAGE_PATH", "/api/v1/acp/messages"),
		AcpStorageDir:        env("POKER_PLAYER_ACP_STORAGE_DIR", "/var/lib/poker-player/acp"),
		AcpDiscoveryScheme:   env("POKER_PLAYER_ACP_DISCOVERY_SCHEME", "http"),
		AcpRelayURL:          strings.TrimSpace(os.Getenv("POKER_PLAYER_ACP_RELAY_URL")),
		AcpAllowInsecureHTTP: boolEnv("POKER_PLAYER_ACP_ALLOW_INSECURE_HTTP", false),
		AcpAllowInsecureTLS:  boolEnv("POKER_PLAYER_ACP_ALLOW_INSECURE_TLS", false),
		AcpAllowInvalidSig:   boolEnv("POKER_PLAYER_ACP_ALLOW_INVALID_SIGNATURE", false),
		AcpCAFile:            strings.TrimSpace(os.Getenv("POKER_PLAYER_ACP_CA_FILE")),
		AcpDeliveryMode:      parseDeliveryMode(env("POKER_PLAYER_ACP_DELIVERY_MODE", "direct")),
		ActionTimeoutMillis:  max(1000, intEnv("POKER_PLAYER_ACTION_TIMEOUT_MILLIS", 12000)),
		OpenAIAPIKey:         strings.TrimSpace(os.Getenv("OPENAI_API_KEY")),
	}
}

func buildAgent(cfg config) (*acp.AcpAgent, error) {
	options := acp.DefaultAgentOptions()
	options.StorageDir = cfg.AcpStorageDir
	options.Endpoint = resolveEndpoint(cfg.PublicBaseURL, cfg.AcpMessagePath)
	options.DiscoveryScheme = cfg.AcpDiscoveryScheme
	options.AllowInsecureHTTP = cfg.AcpAllowInsecureHTTP
	options.AllowInsecureTLS = cfg.AcpAllowInsecureTLS
	options.DefaultDeliveryMode = cfg.AcpDeliveryMode
	if cfg.AcpCAFile != "" {
		options.CAFile = cfg.AcpCAFile
	}
	if cfg.AcpRelayURL != "" {
		options.RelayURL = cfg.AcpRelayURL
		options.RelayHints = []string{cfg.AcpRelayURL}
	}
	agent, err := acp.LoadOrCreate(cfg.LocalAgentID, &options)
	if err != nil {
		return nil, err
	}
	if err := bootstrapPeerIdentity(agent, cfg.DealerAgentID, cfg.AcpDiscoveryScheme); err != nil {
		log.Printf("warning: unable to bootstrap dealer identity %s: %v", cfg.DealerAgentID, err)
	}
	return agent, nil
}

func bootstrapPeerIdentity(agent *acp.AcpAgent, peerAgentID, discoveryScheme string) error {
	parts, err := acp.ParseAgentID(peerAgentID)
	if err != nil {
		return err
	}
	scheme := strings.ToLower(strings.TrimSpace(discoveryScheme))
	if scheme == "" {
		scheme = "https"
	}
	baseURL := fmt.Sprintf("%s://%s", scheme, strings.TrimSpace(parts.Domain))
	wellKnownURL := strings.TrimRight(baseURL, "/") + "/.well-known/acp"
	wellKnownBody, err := fetchJSONMap(wellKnownURL)
	if err != nil {
		return err
	}
	identityReference := strings.TrimSpace(asString(wellKnownBody["identity_document"]))
	if identityReference == "" {
		return fmt.Errorf("well-known document did not include identity_document URL")
	}
	identityURL, err := resolveAbsoluteURL(wellKnownURL, identityReference)
	if err != nil {
		return err
	}
	identityBody, err := fetchJSONMap(identityURL)
	if err != nil {
		return err
	}
	identityDocument, ok := identityBody["identity_document"].(map[string]any)
	if !ok {
		identityDocument = identityBody
	}
	if strings.TrimSpace(asString(identityDocument["agent_id"])) != strings.TrimSpace(peerAgentID) {
		return fmt.Errorf("identity document agent_id mismatch")
	}
	if err := agent.Discovery.RegisterIdentityDocument(identityDocument); err != nil {
		return err
	}
	log.Printf("Bootstrapped ACP identity for %s from %s", peerAgentID, identityURL)
	return nil
}

func fetchJSONMap(rawURL string) (map[string]any, error) {
	request, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	client := &http.Client{Timeout: 8 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status %d", response.StatusCode)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		return nil, err
	}
	return body, nil
}

func resolveAbsoluteURL(sourceURL, target string) (string, error) {
	parsedTarget, err := url.Parse(strings.TrimSpace(target))
	if err != nil {
		return "", err
	}
	if parsedTarget.IsAbs() {
		return parsedTarget.String(), nil
	}
	parsedSource, err := url.Parse(strings.TrimSpace(sourceURL))
	if err != nil {
		return "", err
	}
	return parsedSource.ResolveReference(parsedTarget).String(), nil
}

func newDecisionEngine(cfg config) *decisionEngine {
	return &decisionEngine{
		cfg: cfg,
		http: &http.Client{
			Timeout: time.Duration(cfg.ActionTimeoutMillis) * time.Millisecond,
		},
	}
}

func (engine *decisionEngine) decideAction(request map[string]any) map[string]any {
	personality := resolvePersonality(engine.cfg.Personality, engine.cfg.PlayerID)
	prompt := engine.buildPrompt(request, personality)
	if raw := engine.generateOpenAIDecision(prompt); raw != "" {
		if parsed := engine.parseResponse(raw, request); parsed != nil {
			return parsed
		}
		return engine.safeFallback(request, "invalid-response-fallback")
	}
	return engine.ruleBasedFallback(request, personality, "local-safe-policy")
}

func (engine *decisionEngine) buildPrompt(request map[string]any, p personality) string {
	currentBet := max(0, asInt(request["currentBet"]))
	committedBet := max(0, asInt(request["committedBet"]))
	toCall := max(0, currentBet-committedBet)
	return fmt.Sprintf(`Decide a single Texas Hold'em action for the current player.

Constraints:
- Return STRICT JSON object only.
- Use one of legal actions exactly.
- If action is BET or RAISE, amount must be total bet target for this round.

JSON format:
{"action":"FOLD|CHECK|CALL|BET|RAISE","amount":0,"reason":"short text"}

Context:
tableId=%s
handNumber=%d
round=%s
playerId=%s
holeCards=%v
communityCards=%v
pot=%d
currentBet=%d
committed=%d
toCall=%d
stack=%d
minRaise=%d
legalActions=%v

Personality:
type=%s
bluffFrequency=%.2f
aggressionFactor=%.2f
strategyHint=%s`,
		asString(request["tableId"]),
		asInt(request["handNumber"]),
		asString(request["roundType"]),
		asString(request["playerId"]),
		asStringSlice(request["holeCards"]),
		asStringSlice(request["communityCards"]),
		max(0, asInt(request["pot"])),
		currentBet,
		committedBet,
		toCall,
		max(0, asInt(request["stack"])),
		max(0, asInt(request["minRaise"])),
		legalActionList(request),
		p.Type,
		p.BluffFrequency,
		p.AggressionFactor,
		p.StrategyHint,
	)
}

func (engine *decisionEngine) generateOpenAIDecision(prompt string) string {
	if strings.TrimSpace(prompt) == "" {
		return ""
	}
	if strings.ToLower(strings.TrimSpace(engine.cfg.LLMProvider)) != "openai" {
		return ""
	}
	if engine.cfg.OpenAIAPIKey == "" {
		return ""
	}

	body := map[string]any{
		"model":             firstNonBlank(engine.cfg.Model, "chatgpt-5.2-instant"),
		"max_output_tokens": 220,
		"text":              map[string]any{"verbosity": "low"},
		"input": []any{
			map[string]any{
				"role": "system",
				"content": []any{
					map[string]any{
						"type": "input_text",
						"text": "You are a poker decision engine. Return strict JSON only.",
					},
				},
			},
			map[string]any{
				"role": "user",
				"content": []any{
					map[string]any{
						"type": "input_text",
						"text": prompt,
					},
				},
			},
		},
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return ""
	}

	req, err := http.NewRequest(http.MethodPost, openAIResponsesURL, bytes.NewReader(payload))
	if err != nil {
		return ""
	}
	req.Header.Set("Authorization", "Bearer "+engine.cfg.OpenAIAPIKey)
	req.Header.Set("Content-Type", "application/json")

	res, err := engine.http.Do(req)
	if err != nil {
		log.Printf("OpenAI decision request failed: %v", err)
		return ""
	}
	defer res.Body.Close()

	if res.StatusCode < 200 || res.StatusCode >= 300 {
		log.Printf("OpenAI decision request failed with status %d", res.StatusCode)
		return ""
	}

	var decoded map[string]any
	if err := json.NewDecoder(res.Body).Decode(&decoded); err != nil {
		log.Printf("OpenAI decision response decode failed: %v", err)
		return ""
	}
	return extractOutputText(decoded)
}

func (engine *decisionEngine) parseResponse(raw string, request map[string]any) map[string]any {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil
	}
	start := strings.Index(trimmed, "{")
	end := strings.LastIndex(trimmed, "}")
	if start >= 0 && end > start {
		trimmed = trimmed[start : end+1]
	}

	var payload map[string]any
	if err := json.Unmarshal([]byte(trimmed), &payload); err != nil {
		return nil
	}
	actionName := normalizeActionName(payload["action"])
	if actionName == "" {
		return nil
	}
	action := map[string]any{
		"action": actionName,
		"amount": max(0, asInt(payload["amount"])),
		"reason": optionalString(payload["reason"]),
	}
	if !engine.isActionLegal(action, request) {
		return nil
	}
	return engine.normalizeAction(action, request)
}

func (engine *decisionEngine) normalizeAction(action, request map[string]any) map[string]any {
	actionName := normalizeActionName(action["action"])
	currentBet := max(0, asInt(request["currentBet"]))
	committedBet := max(0, asInt(request["committedBet"]))
	minRaise := max(0, asInt(request["minRaise"]))
	stack := max(0, asInt(request["stack"]))
	toCall := max(0, currentBet-committedBet)
	amount := max(0, asInt(action["amount"]))
	reason := optionalString(action["reason"])

	switch actionName {
	case "FOLD", "CHECK":
		return map[string]any{"action": actionName, "amount": 0, "reason": reason}
	case "CALL":
		return map[string]any{"action": actionName, "amount": min(toCall, stack), "reason": reason}
	case "BET":
		minTarget := max(minRaise, 1)
		maxTarget := committedBet + stack
		return map[string]any{
			"action": actionName,
			"amount": max(minTarget, min(amount, maxTarget)),
			"reason": reason,
		}
	default:
		minTarget := currentBet + minRaise
		maxTarget := committedBet + stack
		return map[string]any{
			"action": "RAISE",
			"amount": max(minTarget, min(amount, maxTarget)),
			"reason": reason,
		}
	}
}

func (engine *decisionEngine) isActionLegal(action, request map[string]any) bool {
	legal := legalActionList(request)
	actionName := normalizeActionName(action["action"])
	if actionName == "" || !contains(legal, actionName) {
		return false
	}
	currentBet := max(0, asInt(request["currentBet"]))
	committedBet := max(0, asInt(request["committedBet"]))
	stack := max(0, asInt(request["stack"]))
	toCall := max(0, currentBet-committedBet)

	switch actionName {
	case "FOLD":
		return true
	case "CHECK":
		return toCall == 0
	case "CALL":
		return stack > 0
	case "BET":
		return currentBet == 0 && stack > 0
	case "RAISE":
		return currentBet > 0 && stack+committedBet > currentBet
	default:
		return false
	}
}

func (engine *decisionEngine) ruleBasedFallback(request map[string]any, p personality, reasonTag string) map[string]any {
	legal := legalActionList(request)
	pot := max(0, asInt(request["pot"]))
	currentBet := max(0, asInt(request["currentBet"]))
	committedBet := max(0, asInt(request["committedBet"]))
	minRaise := max(0, asInt(request["minRaise"]))
	stack := max(0, asInt(request["stack"]))
	toCall := max(0, currentBet-committedBet)
	aggressive := p.AggressionFactor >= 0.7
	bluffing := p.BluffFrequency >= 0.3

	if toCall == 0 {
		if contains(legal, "BET") && (aggressive || bluffing) {
			target := min(committedBet+stack, max(minRaise, minRaise+pot/6))
			return map[string]any{"action": "BET", "amount": max(0, target), "reason": reasonTag + ": pressure bet"}
		}
		return map[string]any{"action": "CHECK", "amount": 0, "reason": reasonTag + ": check"}
	}
	if contains(legal, "CALL") && aggressive && stack > toCall {
		return map[string]any{"action": "CALL", "amount": min(toCall, stack), "reason": reasonTag + ": defend"}
	}
	return map[string]any{"action": "FOLD", "amount": 0, "reason": reasonTag + ": fold"}
}

func (engine *decisionEngine) safeFallback(request map[string]any, reasonTag string) map[string]any {
	legal := legalActionList(request)
	currentBet := max(0, asInt(request["currentBet"]))
	committedBet := max(0, asInt(request["committedBet"]))
	stack := max(0, asInt(request["stack"]))
	toCall := max(0, currentBet-committedBet)

	if toCall > 0 && contains(legal, "FOLD") {
		return map[string]any{"action": "FOLD", "amount": 0, "reason": reasonTag + ": fold"}
	}
	if contains(legal, "CHECK") {
		return map[string]any{"action": "CHECK", "amount": 0, "reason": reasonTag + ": check"}
	}
	if contains(legal, "CALL") {
		return map[string]any{"action": "CALL", "amount": min(toCall, stack), "reason": reasonTag + ": call"}
	}
	if len(legal) > 0 {
		return map[string]any{"action": legal[0], "amount": 0, "reason": reasonTag + ": fallback"}
	}
	return map[string]any{"action": "FOLD", "amount": 0, "reason": reasonTag + ": fallback"}
}

func resolvePersonality(configuredType, playerID string) personality {
	normalized := strings.ToUpper(strings.TrimSpace(configuredType))
	switch normalized {
	case "LOOSE_AGGRESSIVE":
		return personality{Type: "LOOSE_AGGRESSIVE", BluffFrequency: 0.25, AggressionFactor: 0.88, StrategyHint: "Contest many pots and apply pressure often."}
	case "CONSERVATIVE":
		return personality{Type: "CONSERVATIVE", BluffFrequency: 0.05, AggressionFactor: 0.35, StrategyHint: "Avoid marginal spots and preserve stack."}
	case "CHAOTIC":
		return personality{Type: "CHAOTIC", BluffFrequency: 0.45, AggressionFactor: 0.92, StrategyHint: "Mix in unpredictable aggression and occasional bluffs."}
	case "TIGHT_AGGRESSIVE":
		return personality{Type: "TIGHT_AGGRESSIVE", BluffFrequency: 0.10, AggressionFactor: 0.78, StrategyHint: "Play strong ranges and pressure with value-heavy raises."}
	}

	switch strings.ToLower(strings.TrimSpace(playerID)) {
	case "player-1":
		return personality{Type: "TIGHT_AGGRESSIVE", BluffFrequency: 0.10, AggressionFactor: 0.78, StrategyHint: "Play strong ranges and pressure with value-heavy raises."}
	case "player-2":
		return personality{Type: "LOOSE_AGGRESSIVE", BluffFrequency: 0.25, AggressionFactor: 0.88, StrategyHint: "Contest many pots and apply pressure often."}
	case "player-3":
		return personality{Type: "CONSERVATIVE", BluffFrequency: 0.05, AggressionFactor: 0.35, StrategyHint: "Avoid marginal spots and preserve stack."}
	default:
		return personality{Type: "CHAOTIC", BluffFrequency: 0.45, AggressionFactor: 0.92, StrategyHint: "Mix in unpredictable aggression and occasional bluffs."}
	}
}

func (r *runtime) handleACPMessage(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		writeJSON(writer, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var raw map[string]any
	if err := json.NewDecoder(request.Body).Decode(&raw); err != nil {
		writeJSON(writer, http.StatusBadRequest, map[string]any{"error": "invalid json payload"})
		return
	}

	result := r.receive(raw)
	senderID := asString(nestedMap(raw, "envelope")["sender"])
	messageID := asString(nestedMap(raw, "envelope")["message_id"])
	messageClass := strings.ToUpper(strings.TrimSpace(asString(nestedMap(raw, "envelope")["message_class"])))
	if result.DecryptedPayload == nil &&
		result.ReasonCode == string(acp.FailPolicyRejected) &&
		senderID == r.cfg.DealerAgentID &&
		strings.Contains(result.Detail, "DISCOVERY: Unable to resolve identity document") {
		if err := bootstrapPeerIdentity(r.agent, senderID, r.cfg.AcpDiscoveryScheme); err != nil {
			log.Printf(
				"%s ACP inbound discovery bootstrap failed messageId=%s sender=%s err=%v",
				r.cfg.PlayerID,
				messageID,
				senderID,
				err,
			)
		} else {
			log.Printf(
				"%s ACP inbound discovery bootstrap succeeded messageId=%s sender=%s; retrying receive",
				r.cfg.PlayerID,
				messageID,
				senderID,
			)
			result = r.receive(raw)
		}
	}
	if result.DecryptedPayload == nil &&
		result.ReasonCode == string(acp.FailInvalidSignature) &&
		r.cfg.AcpAllowInvalidSig &&
		senderID == r.cfg.DealerAgentID {
		decrypted, decryptErr := r.receiveWithoutSignature(raw)
		if decryptErr != nil {
			log.Printf(
				"%s ACP signature bypass failed messageId=%s sender=%s err=%v",
				r.cfg.PlayerID,
				messageID,
				senderID,
				decryptErr,
			)
		} else {
			result = acp.InboundResult{
				State:            acp.StateAcknowledged,
				Detail:           "signature bypass enabled for demo compatibility",
				DecryptedPayload: decrypted,
			}
			log.Printf(
				"%s ACP inbound signature bypass enabled messageId=%s sender=%s",
				r.cfg.PlayerID,
				messageID,
				senderID,
			)
		}
	}
	log.Printf(
		"%s ACP inbound messageId=%s sender=%s class=%s state=%s reason=%s detail=%s decrypted=%t",
		r.cfg.PlayerID,
		messageID,
		senderID,
		messageClass,
		result.State,
		result.ReasonCode,
		result.Detail,
		result.DecryptedPayload != nil,
	)
	if result.DecryptedPayload != nil {
		r.onInboundPayload(result.DecryptedPayload)
	}
	writeJSON(writer, http.StatusOK, result)
}

func (r *runtime) receiveWithoutSignature(raw map[string]any) (map[string]any, error) {
	message, err := acp.ParseAcpMessage(raw)
	if err != nil {
		return nil, err
	}
	if !containsString(message.Envelope.Recipients, r.agent.AgentID()) {
		return nil, fmt.Errorf("recipient %s not present in envelope", r.agent.AgentID())
	}
	return acp.DecryptForRecipient(
		message.Envelope,
		message.Protected,
		r.agent.AgentID(),
		r.agent.Identity.EncryptionPrivateKey,
	)
}

func (r *runtime) handleWellKnown(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		writeJSON(writer, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	r.mu.Lock()
	doc, err := r.agent.BuildWellKnownDocument(r.cfg.PublicBaseURL, "")
	r.mu.Unlock()
	if err != nil {
		writeJSON(writer, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(writer, http.StatusOK, doc)
}

func (r *runtime) handleIdentity(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		writeJSON(writer, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	r.mu.Lock()
	payload := map[string]any{"identity_document": r.agent.IdentityDocument}
	r.mu.Unlock()
	writeJSON(writer, http.StatusOK, payload)
}

func (r *runtime) receive(raw map[string]any) acp.InboundResult {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.agent.Receive(raw, nil)
}

func (r *runtime) onInboundPayload(payload map[string]any) {
	event := parseInboundEvent(payload)
	if event.Type == "" || event.Payload == nil {
		return
	}

	switch event.Type {
	case "INVITATION":
		response := r.onInvitation(event.Payload)
		r.sendToDealer("JOIN_TABLE", event.TableID, event.HandNumber, asString(response["playerId"]), response)
	case "HAND_START":
		r.mu.Lock()
		r.lastHandNumber = max(0, asInt(nestedMap(event.Payload, "state")["handNumber"]))
		r.mu.Unlock()
		log.Printf("%s received HAND_START for hand %d", r.cfg.PlayerID, r.lastHandNumber)
	case "HOLE_CARDS":
		cards := asStringSlice(event.Payload["holeCards"])
		r.mu.Lock()
		r.holeCards = cards
		r.mu.Unlock()
		log.Printf("%s received hole cards %v", r.cfg.PlayerID, cards)
	case "ACTION_REQUEST":
		response := r.onActionRequest(event.Payload)
		r.sendToDealer("ACTION_RESPONSE", event.TableID, event.HandNumber, asString(response["playerId"]), response)
	case "ACTION_APPLIED":
		log.Printf("%s observed action %v", r.cfg.PlayerID, event.Payload["action"])
	case "COMMUNITY_CARDS_UPDATED":
		log.Printf("%s observed community cards %v", r.cfg.PlayerID, event.Payload["communityCards"])
	case "HAND_RESULT":
		log.Printf(
			"%s received hand result winners=%v payouts=%v",
			r.cfg.PlayerID,
			event.Payload["winnerIds"],
			event.Payload["amountWonByPlayer"],
		)
	case "PLAYER_ELIMINATED":
		if asString(event.Payload["playerId"]) == r.cfg.PlayerID {
			r.mu.Lock()
			r.eliminated = true
			r.mu.Unlock()
			log.Printf("%s has been eliminated", r.cfg.PlayerID)
		}
	case "GAME_FINISHED":
		log.Printf(
			"%s received GAME_FINISHED winner=%v finalStacks=%v",
			r.cfg.PlayerID,
			event.Payload["winnerId"],
			event.Payload["finalStacks"],
		)
	}
}

func (r *runtime) onInvitation(message map[string]any) map[string]any {
	expectedPlayerID := asString(message["playerId"])
	accepted := r.cfg.PlayerID == expectedPlayerID
	log.Printf(
		"%s received INVITATION table=%v seat=%v expectedPlayerId=%q accepted=%t",
		r.cfg.PlayerID,
		message["tableId"],
		message["seatNumber"],
		expectedPlayerID,
		accepted,
	)
	if accepted {
		r.mu.Lock()
		r.activeTableID = asString(message["tableId"])
		r.eliminated = false
		r.mu.Unlock()
	}
	return map[string]any{
		"type":       "JOIN_TABLE",
		"tableId":    message["tableId"],
		"playerId":   r.cfg.PlayerID,
		"seatNumber": max(1, asInt(message["seatNumber"])),
		"accepted":   accepted,
		"message":    map[bool]string{true: "joined", false: "player id mismatch"}[accepted],
	}
}

func (r *runtime) onActionRequest(message map[string]any) map[string]any {
	r.mu.Lock()
	eliminated := r.eliminated
	r.mu.Unlock()

	var action map[string]any
	if eliminated {
		action = map[string]any{"action": "FOLD", "amount": 0, "reason": "eliminated"}
	} else {
		action = r.decision.decideAction(message)
	}
	return map[string]any{
		"type":     "ACTION_RESPONSE",
		"tableId":  message["tableId"],
		"playerId": r.cfg.PlayerID,
		"action":   action,
	}
}

func (r *runtime) sendToDealer(messageType, tableID string, handNumber *int, playerID string, payload map[string]any) {
	encoded := r.encodePayload(messageType, tableID, handNumber, playerID, payload)
	context := "poker:" + firstNonBlank(tableID, "table")

	r.mu.Lock()
	result, err := r.agent.Send(
		[]string{r.cfg.DealerAgentID},
		encoded,
		context,
		acp.MessageSend,
		300,
		"",
		"",
		r.cfg.AcpDeliveryMode,
	)
	r.mu.Unlock()
	if err != nil {
		log.Printf("ACP send failed from %s to dealer: %v", r.cfg.PlayerID, err)
		return
	}
	if isDelivered(result) {
		log.Printf("%s ACP send to dealer delivered messageType=%s table=%s", r.cfg.PlayerID, messageType, tableID)
		return
	}
	log.Printf("ACP send failed from %s to dealer: %s", r.cfg.PlayerID, summarizeFailure(result))
}

func (r *runtime) encodePayload(messageType, tableID string, handNumber *int, playerID string, payload map[string]any) map[string]any {
	r.mu.Lock()
	r.sequence++
	sequence := r.sequence
	r.mu.Unlock()

	event := map[string]any{
		"profile":  pokerProfile,
		"table_id": nullableString(tableID),
		"hand_number": func() any {
			if handNumber == nil {
				return nil
			}
			return *handNumber
		}(),
		"sequence":   sequence,
		"event_type": messageType,
		"player_id":  firstNonBlank(playerID, r.cfg.PlayerID),
		"sent_at":    time.Now().UTC().Format(time.RFC3339Nano),
		"payload":    payload,
	}
	return event
}

func parseInboundEvent(payload map[string]any) inboundEvent {
	if asString(payload["profile"]) == pokerProfile {
		eventType := strings.ToUpper(strings.TrimSpace(asString(payload["event_type"])))
		body, ok := payload["payload"].(map[string]any)
		if ok && eventType != "" {
			tableID := firstNonBlank(asString(payload["table_id"]), asString(body["tableId"]))
			handNumber := intPointer(payload["hand_number"])
			if handNumber == nil {
				handNumber = intPointer(body["handNumber"])
			}
			return inboundEvent{
				Type:       eventType,
				TableID:    tableID,
				HandNumber: handNumber,
				Payload:    body,
			}
		}
	}

	return inboundEvent{
		Type:       strings.ToUpper(strings.TrimSpace(asString(payload["type"]))),
		TableID:    asString(payload["tableId"]),
		HandNumber: intPointer(payload["handNumber"]),
		Payload:    payload,
	}
}

func parseDeliveryMode(configured string) acp.DeliveryMode {
	switch strings.ToLower(strings.TrimSpace(configured)) {
	case "auto":
		return acp.DeliveryAuto
	case "relay":
		return acp.DeliveryRelay
	case "amqp":
		return acp.DeliveryAMQP
	case "mqtt":
		return acp.DeliveryMQTT
	default:
		return acp.DeliveryDirect
	}
}

func legalActionList(request map[string]any) []string {
	raw, ok := request["legalActions"].([]any)
	if !ok {
		return []string{}
	}
	actions := make([]string, 0, len(raw))
	for _, item := range raw {
		normalized := normalizeActionName(item)
		if normalized != "" {
			actions = append(actions, normalized)
		}
	}
	return actions
}

func normalizeActionName(value any) string {
	normalized := strings.ToUpper(strings.TrimSpace(asString(value)))
	if _, ok := legalActions[normalized]; ok {
		return normalized
	}
	return ""
}

func extractOutputText(payload map[string]any) string {
	if text, ok := payload["output_text"].(string); ok && strings.TrimSpace(text) != "" {
		return strings.TrimSpace(text)
	}
	output, ok := payload["output"].([]any)
	if !ok {
		return ""
	}
	pieces := []string{}
	for _, item := range output {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		content, ok := obj["content"].([]any)
		if !ok {
			continue
		}
		for _, part := range content {
			partObj, ok := part.(map[string]any)
			if !ok {
				continue
			}
			text := strings.TrimSpace(asString(partObj["text"]))
			if text != "" {
				pieces = append(pieces, text)
			}
		}
	}
	return strings.Join(pieces, "\n")
}

func isDelivered(result acp.SendResult) bool {
	for _, outcome := range result.Outcomes {
		if outcome.State == acp.StateAcknowledged || outcome.State == acp.StateDelivered {
			return true
		}
	}
	return false
}

func summarizeFailure(result acp.SendResult) string {
	if len(result.Outcomes) == 0 {
		return "no delivery outcomes"
	}
	first := result.Outcomes[0]
	return fmt.Sprintf(
		"state=%s, reasonCode=%v, detail=%v",
		first.State,
		optionalStringPointer(first.ReasonCode),
		optionalStringPointer(first.Detail),
	)
}

func writeJSON(writer http.ResponseWriter, status int, body any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if body == nil {
		return
	}
	encoder := json.NewEncoder(writer)
	if err := encoder.Encode(body); err != nil {
		log.Printf("failed to encode response: %v", err)
	}
}

func env(name, fallback string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	return value
}

func boolEnv(name string, fallback bool) bool {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	switch strings.ToLower(raw) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func intEnv(name string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}

func resolveEndpoint(baseURL, messagePath string) string {
	base := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	path := strings.TrimSpace(messagePath)
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	return base + path
}

func asString(value any) string {
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case fmt.Stringer:
		return strings.TrimSpace(typed.String())
	default:
		return ""
	}
}

func asInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int8:
		return int(typed)
	case int16:
		return int(typed)
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case uint:
		return int(typed)
	case uint8:
		return int(typed)
	case uint16:
		return int(typed)
	case uint32:
		return int(typed)
	case uint64:
		return int(typed)
	case float32:
		return int(typed)
	case float64:
		return int(typed)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err == nil {
			return parsed
		}
		return 0
	default:
		return 0
	}
}

func asStringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		return append([]string{}, typed...)
	case []any:
		output := make([]string, 0, len(typed))
		for _, item := range typed {
			normalized := asString(item)
			if normalized != "" {
				output = append(output, normalized)
			}
		}
		return output
	default:
		return []string{}
	}
}

func optionalString(value any) any {
	normalized := asString(value)
	if normalized == "" {
		return nil
	}
	return normalized
}

func optionalStringPointer(value *string) any {
	if value == nil {
		return nil
	}
	normalized := strings.TrimSpace(*value)
	if normalized == "" {
		return nil
	}
	return normalized
}

func nullableString(value string) any {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil
	}
	return trimmed
}

func intPointer(value any) *int {
	switch value.(type) {
	case nil:
		return nil
	default:
		parsed := asInt(value)
		return &parsed
	}
}

func nestedMap(root map[string]any, key string) map[string]any {
	value, ok := root[key].(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return value
}

func firstNonBlank(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func containsString(values []string, target string) bool {
	return contains(values, target)
}

func min(left, right int) int {
	if left < right {
		return left
	}
	return right
}

func max(left, right int) int {
	if left > right {
		return left
	}
	return right
}

func extractJSONSlice(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}
	start := strings.Index(trimmed, "{")
	end := strings.LastIndex(trimmed, "}")
	if start >= 0 && end > start {
		return trimmed[start : end+1]
	}
	return trimmed
}

func readBodyText(reader io.Reader) string {
	bytesValue, err := io.ReadAll(reader)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(bytesValue))
}
