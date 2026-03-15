package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.ChessPayloadEvent;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.acp.client.AcpAgent;
import org.acp.client.AcpAgentOptions;
import org.acp.client.DeliveryMode;
import org.acp.client.DeliveryOutcome;
import org.acp.client.DeliveryState;
import org.acp.client.InboundResult;
import org.acp.client.SendResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

@Service
public class AcpChessClient {
  private static final Logger log = LoggerFactory.getLogger(AcpChessClient.class);

  private final ChessPlayerProperties properties;
  private final ObjectMapper objectMapper;
  private final AcpAgent agent;
  private final DeliveryMode deliveryMode;

  public AcpChessClient(ChessPlayerProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.objectMapper = objectMapper;
    this.deliveryMode = parseDeliveryMode(properties.getAcpDeliveryMode());
    this.agent = buildAgent();
  }

  public String getLocalAgentId() {
    return properties.getLocalAgentId();
  }

  public Map<String, Object> getIdentityDocument() {
    return agent.getIdentityDocument();
  }

  public Map<String, Object> getWellKnownDocument() {
    return agent.buildWellKnownDocument(properties.getPublicBaseUrl());
  }

  public InboundResult receive(Map<String, Object> rawMessage) {
    return agent.receive(rawMessage, null);
  }

  public boolean sendChessEvent(ChessPayloadEvent event) {
    if (event == null) {
      return false;
    }
    Map<String, Object> payload = objectMapper.convertValue(event, new TypeReference<>() {
    });
    SendResult result = agent.send(
        List.of(properties.getRemoteAgentId()),
        payload,
        "chess:" + event.matchId,
        deliveryMode
    );
    if (result == null || result.getOutcomes() == null || result.getOutcomes().isEmpty()) {
      return false;
    }
    for (DeliveryOutcome outcome : result.getOutcomes()) {
      if (outcome != null
          && (outcome.getState() == DeliveryState.ACKNOWLEDGED || outcome.getState() == DeliveryState.DELIVERED)) {
        return true;
      }
    }
    DeliveryOutcome first = result.getOutcomes().getFirst();
    log.warn(
        "ACP send failed: recipient={}, state={}, reasonCode={}, detail={}",
        first == null ? null : first.getRecipient(),
        first == null ? null : first.getState(),
        first == null ? null : first.getReasonCode(),
        first == null ? null : first.getDetail()
    );
    return false;
  }

  private AcpAgent buildAgent() {
    AcpAgentOptions options = new AcpAgentOptions()
        .setStorageDir(Path.of(properties.getAcpStorageDir()))
        .setEndpoint(properties.resolveAcpEndpoint())
        .setDiscoveryScheme(properties.getAcpDiscoveryScheme())
        .setAllowInsecureHttp(properties.isAcpAllowInsecureHttp())
        .setAllowInsecureTls(properties.isAcpAllowInsecureTls())
        .setCaFile(properties.getAcpCaFile())
        .setDefaultDeliveryMode(deliveryMode);
    if (properties.getAcpRelayUrl() != null && !properties.getAcpRelayUrl().isBlank()) {
      options.setRelayUrl(properties.getAcpRelayUrl());
      options.setRelayHints(List.of(properties.getAcpRelayUrl()));
    }
    return AcpAgent.loadOrCreate(properties.getLocalAgentId(), options);
  }

  private static DeliveryMode parseDeliveryMode(String configured) {
    String normalized = configured == null ? "direct" : configured.trim().toUpperCase();
    try {
      return DeliveryMode.valueOf(normalized);
    } catch (Exception ignored) {
      return DeliveryMode.DIRECT;
    }
  }
}
