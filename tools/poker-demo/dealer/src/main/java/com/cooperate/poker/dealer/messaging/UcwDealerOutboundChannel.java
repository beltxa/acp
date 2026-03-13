package com.cooperate.poker.dealer.messaging;

import com.cooperate.poker.common.messaging.DealerOutboundChannel;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.protocol.ActionAppliedMessage;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.common.protocol.ActionResponseMessage;
import com.cooperate.poker.common.protocol.CommunityCardsUpdatedMessage;
import com.cooperate.poker.common.protocol.GameFinishedMessage;
import com.cooperate.poker.common.protocol.HandResultMessage;
import com.cooperate.poker.common.protocol.HandStartMessage;
import com.cooperate.poker.common.protocol.HoleCardsMessage;
import com.cooperate.poker.common.protocol.InvitationMessage;
import com.cooperate.poker.common.protocol.JoinTableMessage;
import com.cooperate.poker.common.protocol.PokerPayloadCodec;
import com.cooperate.poker.common.protocol.PokerPayloadEvent;
import com.cooperate.poker.common.protocol.PlayerEliminatedMessage;
import com.cooperate.poker.dealer.config.DealerProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import java.net.http.HttpClient;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Component
@ConditionalOnProperty(name = "poker.dealer.transport-mode", havingValue = "UCW", matchIfMissing = true)
public class UcwDealerOutboundChannel implements DealerOutboundChannel {
  private static final Logger log = LoggerFactory.getLogger(UcwDealerOutboundChannel.class);

  private final DealerProperties properties;
  private final RestClient restClient;
  private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();
  private final PokerPayloadCodec payloadCodec;
  private final AtomicReference<UUID> ucwId = new AtomicReference<>();
  private final Set<UUID> processedInboundIds = ConcurrentHashMap.newKeySet();
  private final Map<String, Deque<BufferedActionResponse>> bufferedResponses = new ConcurrentHashMap<>();
  private final AtomicInteger outboundSequence = new AtomicInteger(0);
  private final String correlationId;

  public UcwDealerOutboundChannel(DealerProperties properties) {
    this.properties = properties;
    this.restClient = RestClient.builder()
        .baseUrl(trimTrailingSlash(properties.getCoordinatorBaseUrl()))
        .requestFactory(new JdkClientHttpRequestFactory(buildHttpClient(properties.isInsecureTls())))
        .build();
    this.payloadCodec = new PokerPayloadCodec(objectMapper);
    this.correlationId = properties.getCorrelationIdPrefix() + "-" + properties.getTableId() + "-" + Instant.now().toEpochMilli();
  }

  @Override
  public JoinTableMessage sendInvitation(String playerId, InvitationMessage message) {
    DealerProperties.PlayerUcwIdentity target = requirePlayer(playerId);
    ensureRequiredIdentity(target, playerId);

    UUID ucw = invitePlayer(target);
    boolean joined = waitForParticipantActive(
        ucw,
        target.getParticipantUrn(),
        Duration.ofMillis(properties.getUcwInviteJoinTimeoutMillis())
    );
    String joinMessage = joined ? "joined via UCW" : "join timeout waiting for UCW acceptance";

    return new JoinTableMessage(
        MessageType.JOIN_TABLE,
        message.tableId(),
        playerId,
        message.seatNumber(),
        joined,
        joinMessage
    );
  }

  @Override
  public void sendHandStart(String playerId, HandStartMessage message) {
    sendToPlayer(playerId, message, false);
  }

  @Override
  public void sendHoleCards(String playerId, HoleCardsMessage message) {
    sendToPlayer(playerId, message, false);
  }

  @Override
  public ActionResponseMessage requestAction(String playerId, ActionRequestMessage message) {
    if (!sendToPlayer(playerId, message, true)) {
      return null;
    }

    ActionResponseMessage buffered = drainBufferedResponse(playerId, message.tableId(), message.handNumber());
    if (buffered != null) {
      return buffered;
    }

    Instant deadline = Instant.now().plusMillis(properties.getActionTimeoutMillis());
    while (Instant.now().isBefore(deadline)) {
      pollInboundAndBufferResponses();
      buffered = drainBufferedResponse(playerId, message.tableId(), message.handNumber());
      if (buffered != null) {
        return buffered;
      }
      sleep(properties.getUcwPollIntervalMillis());
    }

    log.warn("Timed out waiting for ACTION_RESPONSE from {} over UCW {}", playerId, ucwId.get());
    return null;
  }

  @Override
  public void broadcastActionApplied(ActionAppliedMessage message) {
    broadcast(message);
  }

  @Override
  public void broadcastCommunityCardsUpdated(CommunityCardsUpdatedMessage message) {
    broadcast(message);
  }

  @Override
  public void broadcastHandResult(HandResultMessage message) {
    broadcast(message);
  }

  @Override
  public void broadcastPlayerEliminated(PlayerEliminatedMessage message) {
    broadcast(message);
  }

  @Override
  public void broadcastGameFinished(GameFinishedMessage message) {
    broadcast(message);
  }

  @Override
  public void closeSession(String reason) {
    UUID currentUcw = ucwId.get();
    if (currentUcw == null) {
      return;
    }

    proposeComplete(currentUcw, reason);

    Instant deadline = Instant.now().plusMillis(properties.getUcwClosureTimeoutMillis());
    while (Instant.now().isBefore(deadline)) {
      UcwDetailView detail = loadUcwDetail(currentUcw);
      String status = normalizeStatus(detail == null || detail.ucw == null ? null : detail.ucw.status);
      if ("CLOSED".equals(status)) {
        log.info("UCW {} closed successfully", currentUcw);
        return;
      }

      if ("FROZEN".equals(status)) {
        acknowledgeComplete(currentUcw, "dealer finalize closure: " + safeReason(reason));
      }

      sleep(properties.getUcwPollIntervalMillis());
    }

    log.warn("UCW {} did not close within {}ms", currentUcw, properties.getUcwClosureTimeoutMillis());
  }

  public UUID getCurrentUcwId() {
    return ucwId.get();
  }

  private void broadcast(Object payload) {
    sendPayload(payload, null, "UCW fanout", false);
  }

  private boolean sendToPlayer(String playerId, Object payload, boolean strict) {
    DealerProperties.PlayerUcwIdentity target = requirePlayer(playerId);
    ensureRequiredIdentity(target, playerId);
    return sendPayload(payload, target.getParticipantUrn(), playerId, strict);
  }

  private boolean sendPayload(
      Object payload,
      String recipientParticipantUrn,
      String destinationLabel,
      boolean strict
  ) {
    UUID currentUcw = ucwId.get();
    if (currentUcw == null) {
      throw new IllegalStateException("No active UCW conversation exists yet");
    }

    OutboundMessageContext context = describePayload(payload);
    String payloadJson = payloadCodec.encode(
        context.messageType(),
        context.tableId(),
        context.handNumber(),
        context.playerId(),
        outboundSequence.incrementAndGet(),
        payload
    );

    SendMessageRequest request = new SendMessageRequest();
    request.recipientParticipantUrn = recipientParticipantUrn;
    request.senderUserUrn = requireNonBlank(properties.getUserUrn(), "poker.dealer.user-urn");
    request.businessProfile = requireNonBlank(properties.getBusinessProfile(), "poker.dealer.business-profile");
    request.payloadFormat = "JSON";
    request.payload = payloadJson;

    try {
      Object responseBody = restClient.post()
          .uri("/api/v1/ucws/{ucwId}/messages", currentUcw)
          .body(commandEnvelope(request, buildCorrelationId("message", currentUcw)))
          .retrieve()
          .body(Object.class);
      OutboundSubmitResponse response = decodeResultData(responseBody, OutboundSubmitResponse.class);
      if (response == null || response.status == null || !"ACCEPTED".equalsIgnoreCase(response.status)) {
        throw new IllegalStateException("UCW send was not accepted for " + destinationLabel);
      }
      return true;
    } catch (ResponseStatusException exception) {
      if (!strict && exception.getStatusCode().value() == 409) {
        if (recipientParticipantUrn == null) {
          log.info("Skipping broadcast message because UCW no longer accepts application messages");
        } else {
          log.info("Skipping message to {} because UCW membership appears inactive", destinationLabel);
        }
        return false;
      }
      throw exception;
    }
  }

  private void pollInboundAndBufferResponses() {
    UUID currentUcw = ucwId.get();
    if (currentUcw == null) {
      return;
    }

    UcwDetailView detail = loadUcwDetail(currentUcw);
    if (detail != null && detail.ucw != null && !matchesBusinessProfile(detail.ucw.businessProfile)) {
      return;
    }
    List<InboundMessageView> inbound = detail == null || detail.inboundMessages == null
        ? List.of()
        : new ArrayList<>(detail.inboundMessages);
    inbound.sort(Comparator.comparing(message -> message.createdAt, Comparator.nullsLast(Comparator.naturalOrder())));

    for (InboundMessageView inboundMessage : inbound) {
      if (inboundMessage == null || inboundMessage.messageId == null) {
        continue;
      }
      if (!processedInboundIds.add(inboundMessage.messageId)) {
        continue;
      }
      if (inboundMessage.payloadText == null || inboundMessage.payloadText.isBlank()) {
        continue;
      }

      PokerPayloadEvent event = payloadCodec.parse(inboundMessage.payloadText).orElse(null);
      if (event == null) {
        continue;
      }
      MessageType type = payloadCodec.resolveMessageType(event).orElse(null);
      if (type != MessageType.ACTION_RESPONSE) {
        continue;
      }

      ActionResponseMessage response = payloadCodec.payloadAs(event, ActionResponseMessage.class).orElse(null);
      if (response == null || response.playerId() == null || response.playerId().isBlank()) {
        continue;
      }
      bufferedResponses
          .computeIfAbsent(response.playerId(), ignored -> new ArrayDeque<>())
          .addLast(new BufferedActionResponse(response, event.tableId(), event.handNumber(), event.sequence()));
    }
  }

  private ActionResponseMessage drainBufferedResponse(String playerId, String expectedTableId, int expectedHandNumber) {
    Deque<BufferedActionResponse> queue = bufferedResponses.get(playerId);
    if (queue == null || queue.isEmpty()) {
      return null;
    }
    while (!queue.isEmpty()) {
      BufferedActionResponse buffered = queue.pollFirst();
      if (buffered == null || buffered.response() == null) {
        continue;
      }
      ActionResponseMessage response = buffered.response();
      if (response.tableId() == null || !response.tableId().equals(expectedTableId)) {
        log.debug(
            "Ignoring ACTION_RESPONSE from {} for table {} while expecting {}",
            playerId,
            response.tableId(),
            expectedTableId
        );
        continue;
      }
      if (buffered.handNumber() != null && buffered.handNumber() != expectedHandNumber) {
        log.debug(
            "Ignoring ACTION_RESPONSE from {} for hand {} while expecting hand {}",
            playerId,
            buffered.handNumber(),
            expectedHandNumber
        );
        continue;
      }
      return response;
    }
    return null;
  }

  private OutboundMessageContext describePayload(Object payload) {
    if (payload instanceof ActionRequestMessage message) {
      return new OutboundMessageContext(MessageType.ACTION_REQUEST, message.tableId(), message.handNumber(), message.playerId());
    }
    if (payload instanceof ActionAppliedMessage message) {
      return new OutboundMessageContext(MessageType.ACTION_APPLIED, message.tableId(), message.handNumber(), message.playerId());
    }
    if (payload instanceof CommunityCardsUpdatedMessage message) {
      return new OutboundMessageContext(MessageType.COMMUNITY_CARDS_UPDATED, message.tableId(), message.handNumber(), null);
    }
    if (payload instanceof GameFinishedMessage message) {
      return new OutboundMessageContext(MessageType.GAME_FINISHED, message.tableId(), null, message.winnerId());
    }
    if (payload instanceof HandResultMessage message) {
      return new OutboundMessageContext(MessageType.HAND_RESULT, message.tableId(), message.handNumber(), null);
    }
    if (payload instanceof HandStartMessage message) {
      return new OutboundMessageContext(
          MessageType.HAND_START,
          message.state().tableId(),
          message.state().handNumber(),
          message.state().currentPlayer()
      );
    }
    if (payload instanceof HoleCardsMessage message) {
      return new OutboundMessageContext(MessageType.HOLE_CARDS, message.tableId(), null, message.playerId());
    }
    if (payload instanceof PlayerEliminatedMessage message) {
      return new OutboundMessageContext(MessageType.PLAYER_ELIMINATED, message.tableId(), null, message.playerId());
    }
    if (payload instanceof InvitationMessage message) {
      return new OutboundMessageContext(MessageType.INVITATION, message.tableId(), null, message.playerId());
    }
    if (payload instanceof JoinTableMessage message) {
      return new OutboundMessageContext(MessageType.JOIN_TABLE, message.tableId(), null, message.playerId());
    }
    throw new IllegalArgumentException("Unsupported UCW payload type: " + payload.getClass().getName());
  }

  private UUID invitePlayer(DealerProperties.PlayerUcwIdentity target) {
    UUID existingUcwId = ucwId.get();
    CreateUcwRequest request = new CreateUcwRequest();
    request.ucwId = existingUcwId;
    request.destinationParticipantUrn = target.getParticipantUrn();
    request.subject = "Poker table invitation " + properties.getTableId();
    request.senderUserUrn = requireNonBlank(properties.getUserUrn(), "poker.dealer.user-urn");
    request.recipientUserUrn = trimToNull(target.getUserUrn());
    request.contextFormat = "JSON";
    request.initialContext = buildInviteInitialContext(target);
    request.businessProfile = requireNonBlank(properties.getBusinessProfile(), "poker.dealer.business-profile");
    if (existingUcwId != null) {
      request.correlationId = correlationId;
    }

    Object responseBody = restClient.post()
        .uri("/api/v1/ucws")
        .body(commandEnvelope(request, firstNonBlank(request.correlationId, buildCorrelationId("ucw-invite", existingUcwId))))
        .retrieve()
        .body(Object.class);
    CreateUcwResponse response = decodeResultData(responseBody, CreateUcwResponse.class);

    if (response == null || response.ucwId == null) {
      throw new IllegalStateException("UCW invite response missing ucwId");
    }

    ucwId.compareAndSet(null, response.ucwId);
    return ucwId.get();
  }

  private boolean waitForParticipantActive(UUID ucwId, String participantUrn, Duration timeout) {
    String expectedParticipantUrn = trimToNull(participantUrn);
    if (expectedParticipantUrn == null) {
      return false;
    }
    Instant deadline = Instant.now().plus(timeout);
    while (Instant.now().isBefore(deadline)) {
      UcwDetailView detail = loadUcwDetail(ucwId);
      if (detail != null && detail.ucw != null && detail.ucw.participants != null) {
        boolean active = detail.ucw.participants.stream()
            .filter(participant -> participant != null)
            .filter(participant -> expectedParticipantUrn.equals(trimToNull(participant.participantUrn)))
            .anyMatch(participant -> participant.active);
        if (active) {
          return true;
        }
      }
      sleep(properties.getUcwPollIntervalMillis());
    }
    return false;
  }

  private UcwDetailView loadUcwDetail(UUID ucwId) {
    UcwDetailView detail = restClient.get()
        .uri("/api/v1/ucws/{ucwId}", ucwId)
        .retrieve()
        .body(UcwDetailView.class);
    if (detail == null) {
      throw new IllegalStateException("UCW detail response is empty for " + ucwId);
    }
    if (detail.inboundMessages == null) {
      detail.inboundMessages = List.of();
    }
    return detail;
  }

  private void proposeComplete(UUID ucwId, String reason) {
    NoteRequest request = new NoteRequest();
    request.note = "dealer proposes completion: " + safeReason(reason);
    restClient.post()
        .uri("/api/v1/ucws/{ucwId}/close-proposals", ucwId)
        .body(commandEnvelope(request, buildCorrelationId("close-proposal", ucwId)))
        .retrieve()
        .toBodilessEntity();
  }

  private void acknowledgeComplete(UUID ucwId, String reason) {
    CloseVoteRequest request = new CloseVoteRequest();
    request.accept = true;
    request.note = reason;
    try {
      restClient.post()
          .uri("/api/v1/ucws/{ucwId}/close-proposals/{proposalId}/votes", ucwId, "latest")
          .body(commandEnvelope(request, buildCorrelationId("close-vote", ucwId)))
          .retrieve()
          .toBodilessEntity();
    } catch (ResponseStatusException exception) {
      if (exception.getStatusCode().value() != 409) {
        throw exception;
      }
    }
  }

  private static String normalizeStatus(String status) {
    if (status == null) {
      return "";
    }
    return status.trim().toUpperCase(Locale.ROOT);
  }

  private DealerProperties.PlayerUcwIdentity requirePlayer(String playerId) {
    DealerProperties.PlayerUcwIdentity player = properties.getPlayerUcw().get(playerId);
    if (player == null) {
      throw new IllegalArgumentException("Missing UCW identity for player " + playerId + " (poker.dealer.player-ucw)");
    }
    return player;
  }

  private void ensureRequiredIdentity(DealerProperties.PlayerUcwIdentity target, String playerId) {
    requireNonBlank(target.getParticipantUrn(), "poker.dealer.player-ucw." + playerId + ".participant-urn");
  }

  private static String requireNonBlank(String value, String fieldName) {
    if (value == null || value.isBlank()) {
      throw new IllegalStateException(fieldName + " must be configured");
    }
    return value.trim();
  }

  private static String safeReason(String reason) {
    return reason == null || reason.isBlank() ? "poker game completed" : reason;
  }

  private static void sleep(int millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException interruptedException) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("Interrupted while waiting for UCW event", interruptedException);
    }
  }

  private static HttpClient buildHttpClient(boolean insecureTls) {
    HttpClient.Builder builder = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10));
    if (!insecureTls) {
      return builder.build();
    }

    try {
      TrustManager[] trustAll = new TrustManager[]{new X509TrustManager() {
        @Override
        public void checkClientTrusted(X509Certificate[] chain, String authType) {
        }

        @Override
        public void checkServerTrusted(X509Certificate[] chain, String authType) {
        }

        @Override
        public X509Certificate[] getAcceptedIssuers() {
          return new X509Certificate[0];
        }
      }};
      SSLContext sslContext = SSLContext.getInstance("TLS");
      sslContext.init(null, trustAll, new SecureRandom());
      SSLParameters sslParameters = new SSLParameters();
      sslParameters.setEndpointIdentificationAlgorithm(null);
      return builder.sslContext(sslContext).sslParameters(sslParameters).build();
    } catch (Exception exception) {
      log.warn("Failed to initialize insecure TLS client, falling back to default TLS", exception);
      return builder.build();
    }
  }

  private static String trimTrailingSlash(String value) {
    if (value == null || value.isBlank()) {
      return "";
    }
    return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
  }

  private boolean matchesBusinessProfile(String businessProfile) {
    String expected = trimToNull(properties.getBusinessProfile());
    if (expected == null) {
      return true;
    }
    return expected.equals(trimToNull(businessProfile));
  }

  private static String trimToNull(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    return value.trim();
  }

  private <T> T decodeResultData(Object responseBody, Class<T> targetType) {
    if (responseBody == null) {
      return null;
    }
    if (!(responseBody instanceof Map<?, ?> map)) {
      throw new IllegalStateException("Coordinator response is not an operation result envelope");
    }
    if (!map.containsKey("data")) {
      throw new IllegalStateException("Coordinator response envelope is missing data");
    }
    Object data = map.get("data");
    if (data == null) {
      return null;
    }
    return objectMapper.convertValue(data, targetType);
  }

  private <T> CommandEnvelope<T> commandEnvelope(T payload, String correlationId) {
    CommandEnvelope<T> envelope = new CommandEnvelope<>();
    OperationMetadata metadata = new OperationMetadata();
    metadata.correlationId = firstNonBlank(correlationId, "poker-dealer-" + UUID.randomUUID());
    envelope.metadata = metadata;
    envelope.payload = payload;
    return envelope;
  }

  private String buildCorrelationId(String operation, UUID ucwId) {
    String scope = ucwId == null ? properties.getTableId() : ucwId.toString();
    return "poker-dealer-" + operation + "-" + scope + "-" + Instant.now().toEpochMilli();
  }

  private String buildInviteInitialContext(DealerProperties.PlayerUcwIdentity target) {
    Map<String, Object> context = new LinkedHashMap<>();
    context.put("kind", "POKER_INVITATION");
    context.put("tableId", properties.getTableId());
    context.put("businessProfile", requireNonBlank(properties.getBusinessProfile(), "poker.dealer.business-profile"));
    context.put("targetParticipantUrn", target.getParticipantUrn());
    String targetUserUrn = trimToNull(target.getUserUrn());
    if (targetUserUrn != null) {
      context.put("targetUserUrn", targetUserUrn);
    }
    context.put("sentAt", Instant.now().toString());
    try {
      return objectMapper.writeValueAsString(context);
    } catch (Exception exception) {
      throw new IllegalStateException("Failed to encode invite initial context", exception);
    }
  }

  private static String firstNonBlank(String preferred, String fallback) {
    if (preferred != null && !preferred.isBlank()) {
      return preferred.trim();
    }
    return fallback;
  }

  private static class CreateUcwRequest {
    @JsonProperty("destinationParticipantUrn")
    public String destinationParticipantUrn;

    @JsonProperty("ucwId")
    public UUID ucwId;

    @JsonProperty("correlationId")
    public String correlationId;

    @JsonProperty("businessProfile")
    public String businessProfile;

    @JsonProperty("subject")
    public String subject;

    @JsonProperty("senderUserUrn")
    public String senderUserUrn;

    @JsonProperty("recipientUserUrn")
    public String recipientUserUrn;

    @JsonProperty("contextFormat")
    public String contextFormat;

    @JsonProperty("initialContext")
    public String initialContext;
  }

  private static class CreateUcwResponse {
    @JsonProperty("ucwId")
    public UUID ucwId;
  }

  private static class SendMessageRequest {
    public String recipientParticipantUrn;

    public String senderUserUrn;

    public String businessProfile;

    public String payloadFormat;

    public String payload;
  }

  private static class OutboundSubmitResponse {
    @JsonProperty("status")
    public String status;
  }

  private static class NoteRequest {
    public String note;
  }

  private static class CloseVoteRequest {
    public Boolean accept;
    public String note;
  }

  private static class OperationMetadata {
    public String correlationId;
    public String idempotencyKey;
  }

  private static class CommandEnvelope<T> {
    public OperationMetadata metadata;
    public T payload;
  }

  private static class UcwDetailView {
    @JsonProperty("ucw")
    public UcwDetail ucw;

    @JsonProperty("inboundMessages")
    public List<InboundMessageView> inboundMessages = List.of();
  }

  private static class UcwDetail {
    @JsonProperty("status")
    public String status;

    @JsonProperty("businessProfile")
    public String businessProfile;

    @JsonProperty("participants")
    public List<UcwParticipant> participants = List.of();
  }

  private static class UcwParticipant {
    @JsonProperty("participantUrn")
    public String participantUrn;

    @JsonProperty("active")
    public boolean active;
  }

  private static class InboundMessageView {
    @JsonProperty("messageId")
    public UUID messageId;

    @JsonProperty("createdAt")
    public Instant createdAt;

    @JsonProperty("payloadText")
    public String payloadText;
  }

  private record BufferedActionResponse(
      ActionResponseMessage response,
      String tableId,
      Integer handNumber,
      Integer sequence
  ) {
  }

  private record OutboundMessageContext(
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String playerId
  ) {
  }
}
