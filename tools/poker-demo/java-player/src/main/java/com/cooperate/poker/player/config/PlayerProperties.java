package com.cooperate.poker.player.config;

import com.cooperate.poker.common.model.PersonalityType;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "poker.player")
public class PlayerProperties {

  @NotBlank
  private String transportMode = "ACP";

  @NotBlank
  private String playerId = "Player-1";

  @NotBlank
  private String entityId = "Entity-A";

  private PersonalityType personality = PersonalityType.TIGHT_AGGRESSIVE;

  @NotBlank
  private String llmProvider = "openai";

  @NotBlank
  private String model = "chatgpt-5.2-instant";

  @NotBlank
  private String localAgentId = "agent:player1@localhost:8091";

  @NotBlank
  private String dealerAgentId = "agent:dealer@localhost:8090";

  @NotBlank
  private String publicBaseUrl = "http://localhost:8091";

  @NotBlank
  private String acpMessagePath = "/api/v1/acp/messages";

  @NotBlank
  private String acpStorageDir = "/var/lib/poker-player/acp";

  @NotBlank
  private String acpDiscoveryScheme = "http";

  private String acpRelayUrl;
  private boolean acpAllowInsecureHttp = true;
  private boolean acpAllowInsecureTls = false;
  private String acpCaFile;

  @NotBlank
  private String acpDeliveryMode = "direct";

  private String openaiApiKey;
  private String claudeApiKey;

  @Min(1000)
  private int actionTimeoutMillis = 12000;

  @NotBlank
  private String coordinatorBaseUrl = "https://coordinator-b:8082";

  private boolean insecureTls = true;

  @NotBlank
  private String participantUrn = "urn:co-operator:entity:000002";

  @NotBlank
  private String userUrn = "urn:cooperate:entityA:00001";

  @NotBlank
  private String dealerParticipantUrn = "urn:co-operator:entity:000005";

  private boolean autoAcceptPendingInvites = true;

  @Min(200)
  private long ucwPollIntervalMillis = 1200;

  @NotBlank
  private String businessProfile = "co-operate:poker";

  public String getTransportMode() {
    return transportMode;
  }

  public void setTransportMode(String transportMode) {
    this.transportMode = transportMode;
  }

  public String getPlayerId() {
    return playerId;
  }

  public void setPlayerId(String playerId) {
    this.playerId = playerId;
  }

  public String getEntityId() {
    return entityId;
  }

  public void setEntityId(String entityId) {
    this.entityId = entityId;
  }

  public PersonalityType getPersonality() {
    return personality;
  }

  public void setPersonality(PersonalityType personality) {
    this.personality = personality;
  }

  public String getLlmProvider() {
    return llmProvider;
  }

  public void setLlmProvider(String llmProvider) {
    this.llmProvider = llmProvider;
  }

  public String getModel() {
    return model;
  }

  public void setModel(String model) {
    this.model = model;
  }

  public String getLocalAgentId() {
    return localAgentId;
  }

  public void setLocalAgentId(String localAgentId) {
    this.localAgentId = localAgentId;
  }

  public String getDealerAgentId() {
    return dealerAgentId;
  }

  public void setDealerAgentId(String dealerAgentId) {
    this.dealerAgentId = dealerAgentId;
  }

  public String getPublicBaseUrl() {
    return publicBaseUrl;
  }

  public void setPublicBaseUrl(String publicBaseUrl) {
    this.publicBaseUrl = publicBaseUrl;
  }

  public String getAcpMessagePath() {
    return acpMessagePath;
  }

  public void setAcpMessagePath(String acpMessagePath) {
    this.acpMessagePath = acpMessagePath;
  }

  public String getAcpStorageDir() {
    return acpStorageDir;
  }

  public void setAcpStorageDir(String acpStorageDir) {
    this.acpStorageDir = acpStorageDir;
  }

  public String getAcpDiscoveryScheme() {
    return acpDiscoveryScheme;
  }

  public void setAcpDiscoveryScheme(String acpDiscoveryScheme) {
    this.acpDiscoveryScheme = acpDiscoveryScheme;
  }

  public String getAcpRelayUrl() {
    return acpRelayUrl;
  }

  public void setAcpRelayUrl(String acpRelayUrl) {
    this.acpRelayUrl = acpRelayUrl;
  }

  public boolean isAcpAllowInsecureHttp() {
    return acpAllowInsecureHttp;
  }

  public void setAcpAllowInsecureHttp(boolean acpAllowInsecureHttp) {
    this.acpAllowInsecureHttp = acpAllowInsecureHttp;
  }

  public boolean isAcpAllowInsecureTls() {
    return acpAllowInsecureTls;
  }

  public void setAcpAllowInsecureTls(boolean acpAllowInsecureTls) {
    this.acpAllowInsecureTls = acpAllowInsecureTls;
  }

  public String getAcpCaFile() {
    return acpCaFile;
  }

  public void setAcpCaFile(String acpCaFile) {
    this.acpCaFile = acpCaFile;
  }

  public String getAcpDeliveryMode() {
    return acpDeliveryMode;
  }

  public void setAcpDeliveryMode(String acpDeliveryMode) {
    this.acpDeliveryMode = acpDeliveryMode;
  }

  public String getOpenaiApiKey() {
    return openaiApiKey;
  }

  public void setOpenaiApiKey(String openaiApiKey) {
    this.openaiApiKey = openaiApiKey;
  }

  public String getClaudeApiKey() {
    return claudeApiKey;
  }

  public void setClaudeApiKey(String claudeApiKey) {
    this.claudeApiKey = claudeApiKey;
  }

  public int getActionTimeoutMillis() {
    return actionTimeoutMillis;
  }

  public void setActionTimeoutMillis(int actionTimeoutMillis) {
    this.actionTimeoutMillis = actionTimeoutMillis;
  }

  public String getCoordinatorBaseUrl() {
    return coordinatorBaseUrl;
  }

  public void setCoordinatorBaseUrl(String coordinatorBaseUrl) {
    this.coordinatorBaseUrl = coordinatorBaseUrl;
  }

  public boolean isInsecureTls() {
    return insecureTls;
  }

  public void setInsecureTls(boolean insecureTls) {
    this.insecureTls = insecureTls;
  }

  public String getParticipantUrn() {
    return participantUrn;
  }

  public void setParticipantUrn(String participantUrn) {
    this.participantUrn = participantUrn;
  }

  public String getUserUrn() {
    return userUrn;
  }

  public void setUserUrn(String userUrn) {
    this.userUrn = userUrn;
  }

  public String getDealerParticipantUrn() {
    return dealerParticipantUrn;
  }

  public void setDealerParticipantUrn(String dealerParticipantUrn) {
    this.dealerParticipantUrn = dealerParticipantUrn;
  }

  public boolean isAutoAcceptPendingInvites() {
    return autoAcceptPendingInvites;
  }

  public void setAutoAcceptPendingInvites(boolean autoAcceptPendingInvites) {
    this.autoAcceptPendingInvites = autoAcceptPendingInvites;
  }

  public long getUcwPollIntervalMillis() {
    return ucwPollIntervalMillis;
  }

  public void setUcwPollIntervalMillis(long ucwPollIntervalMillis) {
    this.ucwPollIntervalMillis = ucwPollIntervalMillis;
  }

  public String getBusinessProfile() {
    return businessProfile;
  }

  public void setBusinessProfile(String businessProfile) {
    this.businessProfile = businessProfile;
  }

  public String resolveAcpEndpoint() {
    String base = publicBaseUrl == null ? "" : publicBaseUrl.trim();
    String path = acpMessagePath == null ? "" : acpMessagePath.trim();
    if (base.endsWith("/") && path.startsWith("/")) {
      return base.substring(0, base.length() - 1) + path;
    }
    if (!base.endsWith("/") && !path.startsWith("/")) {
      return base + "/" + path;
    }
    return base + path;
  }
}
