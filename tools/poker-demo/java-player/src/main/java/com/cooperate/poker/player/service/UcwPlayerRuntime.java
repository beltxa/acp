package com.cooperate.poker.player.service;

import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.protocol.ActionAppliedMessage;
import com.cooperate.poker.common.protocol.ActionRequestMessage;
import com.cooperate.poker.common.protocol.ActionResponseMessage;
import com.cooperate.poker.common.protocol.CommunityCardsUpdatedMessage;
import com.cooperate.poker.common.protocol.GameFinishedMessage;
import com.cooperate.poker.common.protocol.HandResultMessage;
import com.cooperate.poker.common.protocol.HandStartMessage;
import com.cooperate.poker.common.protocol.HoleCardsMessage;
import com.cooperate.poker.common.protocol.PokerPayloadCodec;
import com.cooperate.poker.common.protocol.PokerPayloadEvent;
import com.cooperate.poker.common.protocol.PlayerEliminatedMessage;
import com.cooperate.poker.player.config.PlayerProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
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
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Component
@ConditionalOnProperty(name = "poker.player.transport-mode", havingValue = "UCW", matchIfMissing = true)
public class UcwPlayerRuntime {
  private static final Logger log = LoggerFactory.getLogger(UcwPlayerRuntime.class);

  private final PlayerProperties properties;
  private final PlayerService playerService;
  private final RestClient restClient;
  private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();
  private final PokerPayloadCodec payloadCodec;
  private final AtomicReference<UUID> activeUcwId = new AtomicReference<>();
  private final Set<UUID> processedInboundIds = ConcurrentHashMap.newKeySet();
  private final AtomicInteger outboundSequence = new AtomicInteger(0);

  public UcwPlayerRuntime(PlayerProperties properties, PlayerService playerService) {
    this.properties = properties;
    this.playerService = playerService;
    this.restClient = RestClient.builder()
        .baseUrl(trimTrailingSlash(properties.getCoordinatorBaseUrl()))
        .requestFactory(new JdkClientHttpRequestFactory(buildHttpClient(properties.isInsecureTls())))
        .build();
    this.payloadCodec = new PokerPayloadCodec(objectMapper);
  }

  @Scheduled(fixedDelayString = "${poker.player.ucw-poll-interval-millis:1200}")
  public void pollUcw() {
    try {
      ensureJoinedUcw();
      UUID ucwId = activeUcwId.get();
      if (ucwId == null) {
        return;
      }

      UcwDetailView detail = loadUcwDetail(ucwId);
      String status = normalizeStatus(detail == null || detail.ucw == null ? null : detail.ucw.status);
      if ("CLOSED".equals(status)) {
        log.info("{} observed UCW {} closed", properties.getPlayerId(), ucwId);
        activeUcwId.compareAndSet(ucwId, null);
        processedInboundIds.clear();
        return;
      }

      processInboundMessages(ucwId, detail);
    } catch (Exception exception) {
      log.warn("UCW poll failed for {}", properties.getPlayerId(), exception);
    }
  }

  private void ensureJoinedUcw() {
    if (activeUcwId.get() != null) {
      return;
    }
    if (!properties.isAutoAcceptPendingInvites()) {
      return;
    }

    for (UcwSummaryView summary : listPendingInvites()) {
      if (summary == null || summary.ucwId == null) {
        continue;
      }

      UcwDetailView detail = loadUcwDetail(summary.ucwId);
      String status = normalizeStatus(detail != null && detail.ucw != null ? detail.ucw.status : null);
      if ("CLOSED".equals(status)) {
        log.debug("{} skipping stale invite {} because UCW is CLOSED", properties.getPlayerId(), summary.ucwId);
        continue;
      }
      String businessProfile = detail != null && detail.ucw != null ? detail.ucw.businessProfile : null;
      if (!matchesBusinessProfile(businessProfile)) {
        continue;
      }

      if (!respondInvite(summary.ucwId, true)) {
        continue;
      }
      activeUcwId.set(summary.ucwId);
      processedInboundIds.clear();
      log.info("{} accepted UCW invite {}", properties.getPlayerId(), summary.ucwId);
      return;
    }
  }

  private void processInboundMessages(UUID ucwId, UcwDetailView detail) {
    if (detail != null && detail.ucw != null && !matchesBusinessProfile(detail.ucw.businessProfile)) {
      return;
    }
    List<InboundMessageView> inboundMessages = detail == null || detail.inboundMessages == null
        ? List.of()
        : new ArrayList<>(detail.inboundMessages);
    inboundMessages.sort(Comparator.comparing(message -> message.createdAt, Comparator.nullsLast(Comparator.naturalOrder())));

    for (InboundMessageView inbound : inboundMessages) {
      if (inbound == null || inbound.messageId == null || inbound.payloadText == null || inbound.payloadText.isBlank()) {
        continue;
      }
      if (!processedInboundIds.add(inbound.messageId)) {
        continue;
      }

      PokerPayloadEvent event = payloadCodec.parse(inbound.payloadText).orElse(null);
      if (event == null) {
        continue;
      }
      MessageType type = payloadCodec.resolveMessageType(event).orElse(null);
      if (type == null) {
        continue;
      }

      try {
        switch (type) {
          case HAND_START -> payloadCodec.payloadAs(event, HandStartMessage.class)
              .ifPresent(playerService::onHandStart);
          case HOLE_CARDS -> payloadCodec.payloadAs(event, HoleCardsMessage.class)
              .ifPresent(playerService::onHoleCards);
          case ACTION_REQUEST -> {
            ActionRequestMessage request = payloadCodec.payloadAs(event, ActionRequestMessage.class).orElse(null);
            if (request == null) {
              continue;
            }
            ActionResponseMessage response = playerService.onActionRequest(request);
            sendMessage(
                ucwId,
                null,
                response,
                MessageType.ACTION_RESPONSE,
                request.tableId(),
                request.handNumber(),
                response.playerId()
            );
          }
          case ACTION_APPLIED -> payloadCodec.payloadAs(event, ActionAppliedMessage.class)
              .ifPresent(playerService::onActionApplied);
          case COMMUNITY_CARDS_UPDATED -> payloadCodec.payloadAs(event, CommunityCardsUpdatedMessage.class)
              .ifPresent(playerService::onCommunityCardsUpdated);
          case HAND_RESULT -> payloadCodec.payloadAs(event, HandResultMessage.class)
              .ifPresent(playerService::onHandResult);
          case PLAYER_ELIMINATED -> payloadCodec.payloadAs(event, PlayerEliminatedMessage.class)
              .ifPresent(eliminatedMessage -> {
                playerService.onPlayerEliminated(eliminatedMessage);
                if (properties.getPlayerId().equals(eliminatedMessage.playerId())) {
                  requestLeave(ucwId);
                  activeUcwId.compareAndSet(ucwId, null);
                }
              });
          case GAME_FINISHED -> payloadCodec.payloadAs(event, GameFinishedMessage.class)
              .ifPresent(gameFinishedMessage -> {
                playerService.onGameFinished(gameFinishedMessage);
                if (!playerService.isEliminated()) {
                  acknowledgeComplete(ucwId, properties.getPlayerId() + " acknowledges poker game closure");
                }
              });
          case INVITATION, JOIN_TABLE, ACTION_RESPONSE -> {
            // Not expected as inbound gameplay events for player runtime.
          }
        }
      } catch (Exception exception) {
        log.warn("Failed to process inbound UCW message {} for {}", inbound.messageId, properties.getPlayerId(), exception);
      }
    }
  }

  private void sendMessage(
      UUID ucwId,
      String recipientParticipantUrn,
      Object payload,
      MessageType messageType,
      String tableId,
      Integer handNumber,
      String playerId
  ) {
    String payloadJson = payloadCodec.encode(
        messageType,
        tableId,
        handNumber,
        playerId,
        outboundSequence.incrementAndGet(),
        payload
    );

    SendMessageRequest request = new SendMessageRequest();
    request.recipientParticipantUrn = recipientParticipantUrn;
    request.senderUserUrn = requireNonBlank(properties.getUserUrn(), "poker.player.user-urn");
    request.businessProfile = requireNonBlank(properties.getBusinessProfile(), "poker.player.business-profile");
    request.payloadFormat = "JSON";
    request.payload = payloadJson;

    Object responseBody = restClient.post()
        .uri("/api/v1/ucws/{ucwId}/messages", ucwId)
        .body(commandEnvelope(request, buildCorrelationId("message", ucwId)))
        .retrieve()
        .body(Object.class);
    OutboundSubmitResponse response = decodeResultData(responseBody, OutboundSubmitResponse.class);
    if (response == null || response.status == null || !"ACCEPTED".equalsIgnoreCase(response.status)) {
      throw new IllegalStateException("UCW action response send was not accepted");
    }
  }

  private boolean respondInvite(UUID ucwId, boolean accept) {
    InvitationResponseRequest request = new InvitationResponseRequest();
    request.accept = accept;

    try {
      restClient.post()
          .uri("/api/v1/ucws/{ucwId}/invitation-responses", ucwId)
          .body(commandEnvelope(request, buildCorrelationId("invitation-response", ucwId)))
          .retrieve()
          .toBodilessEntity();
      return true;
    } catch (HttpClientErrorException exception) {
      if (exception.getStatusCode().value() == 409 && isClosedUcwConflict(exception.getResponseBodyAsString())) {
        log.info("{} ignoring stale invite {} because UCW is already CLOSED", properties.getPlayerId(), ucwId);
        return false;
      }
      throw exception;
    }
  }

  private void requestLeave(UUID ucwId) {
    try {
      restClient.post()
          .uri("/api/v1/ucws/{ucwId}/leave-notices", ucwId)
          .body(commandEnvelope(new LeaveNoticeRequest(), buildCorrelationId("leave-notice", ucwId)))
          .retrieve()
          .toBodilessEntity();
      log.info("{} requested leave from UCW {}", properties.getPlayerId(), ucwId);
    } catch (ResponseStatusException exception) {
      if (exception.getStatusCode().value() != 409) {
        throw exception;
      }
    }
  }

  private void acknowledgeComplete(UUID ucwId, String note) {
    CloseVoteRequest request = new CloseVoteRequest();
    request.accept = true;
    request.note = note;

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

  private List<UcwSummaryView> listPendingInvites() {
    List<UcwSummaryView> primary = listUcws("INVITED_PENDING");
    if (!primary.isEmpty()) {
      return primary;
    }
    return listUcws("PENDING");
  }

  private List<UcwSummaryView> listUcws(String invitationStatus) {
    String uri = "/api/v1/ucws?offset=0&limit=200&invitationStatus=" + invitationStatus;
    List<UcwSummaryView> rows = restClient.get()
        .uri(uri)
        .retrieve()
        .body(new ParameterizedTypeReference<>() {
        });
    return rows == null ? List.of() : rows;
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

  private boolean matchesBusinessProfile(String businessProfile) {
    String expected = trimToNull(properties.getBusinessProfile());
    if (expected == null) {
      return true;
    }
    return expected.equals(trimToNull(businessProfile));
  }

  private static String normalizeStatus(String status) {
    if (status == null) {
      return "";
    }
    return status.trim().toUpperCase(Locale.ROOT);
  }

  private static String requireNonBlank(String value, String fieldName) {
    if (value == null || value.isBlank()) {
      throw new IllegalStateException(fieldName + " must be configured");
    }
    return value.trim();
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

  private static String trimToNull(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    return value.trim();
  }

  private static boolean isClosedUcwConflict(String responseBody) {
    if (responseBody == null || responseBody.isBlank()) {
      return false;
    }
    return responseBody.toUpperCase(Locale.ROOT).contains("UCW IS CLOSED");
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
    metadata.correlationId = firstNonBlank(correlationId, "poker-player-" + UUID.randomUUID());
    envelope.metadata = metadata;
    envelope.payload = payload;
    return envelope;
  }

  private String buildCorrelationId(String operation, UUID ucwId) {
    String scope = ucwId == null ? properties.getPlayerId() : ucwId.toString();
    return "poker-player-" + operation + "-" + scope + "-" + Instant.now().toEpochMilli();
  }

  private static String firstNonBlank(String preferred, String fallback) {
    if (preferred != null && !preferred.isBlank()) {
      return preferred.trim();
    }
    return fallback;
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

  private static class LeaveNoticeRequest {
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

  private static class InvitationResponseRequest {
    public boolean accept;
  }

  private static class CloseVoteRequest {
    public Boolean accept;
    public String note;
  }

  private static class UcwSummaryView {
    @JsonProperty("ucwId")
    public UUID ucwId;
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

    @JsonProperty("ucwCorrelationId")
    public String ucwCorrelationId;
  }

  private static class InboundMessageView {
    @JsonProperty("messageId")
    public UUID messageId;

    @JsonProperty("createdAt")
    public Instant createdAt;

    @JsonProperty("payloadText")
    public String payloadText;
  }
}
