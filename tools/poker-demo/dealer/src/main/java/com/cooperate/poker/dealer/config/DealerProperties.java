package com.cooperate.poker.dealer.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.util.LinkedHashMap;
import java.util.Map;

@Validated
@ConfigurationProperties(prefix = "poker.dealer")
public class DealerProperties {

  @NotBlank
  private String transportMode = "ACP";

  @NotBlank
  private String tableId = "table-1";

  @Min(10)
  private int startingStack = 100;

  @Min(1)
  private int smallBlind = 5;

  @Min(2)
  private int bigBlind = 10;

  @Min(0)
  private int ante = 5;

  @Min(0)
  private int spectatorDelayMillis = 1500;

  @Min(1)
  private int actionTimeoutMillis = 15000;

  @Min(2)
  private int seatCount = 4;

  private boolean demoVisibilityMode = true;

  @Min(1)
  private int maxHands = 200;

  @NotBlank
  private String coordinatorBaseUrl = "https://coordinator-a:8082";

  private boolean insecureTls = true;

  @NotBlank
  private String participantUrn = "urn:co-operator:entity:000005";

  @NotBlank
  private String userUrn = "urn:cooperate:dealer:00001";

  @NotBlank
  private String businessProfile = "co-operate:poker";

  @NotBlank
  private String localAgentId = "agent:dealer@localhost:8090";

  @NotBlank
  private String publicBaseUrl = "http://localhost:8090";

  @NotBlank
  private String acpMessagePath = "/api/v1/acp/messages";

  @NotBlank
  private String acpStorageDir = "/var/lib/poker-dealer/acp";

  @NotBlank
  private String acpDiscoveryScheme = "http";

  private String acpRelayUrl;
  private boolean acpAllowInsecureHttp = true;
  private boolean acpAllowInsecureTls = false;
  private String acpCaFile;

  @NotBlank
  private String acpDeliveryMode = "direct";

  @Min(20)
  private int acpPollIntervalMillis = 100;

  @Min(500)
  private int inviteTimeoutMillis = 20000;

  @NotBlank
  private String correlationIdPrefix = "poker";

  @Min(200)
  private int ucwPollIntervalMillis = 1000;

  @Min(2000)
  private int ucwInviteJoinTimeoutMillis = 20000;

  @Min(2000)
  private int ucwClosureTimeoutMillis = 45000;

  @NotEmpty
  private Map<String, String> playerEndpoints = new LinkedHashMap<>();

  @NotEmpty
  private Map<String, String> playerAgentIds = new LinkedHashMap<>();

  private Map<String, PlayerUcwIdentity> playerUcw = new LinkedHashMap<>();

  public DealerProperties() {
    playerEndpoints.put("Player-1", "http://localhost:8091");
    playerEndpoints.put("Player-2", "http://localhost:8092");
    playerEndpoints.put("Player-3", "http://localhost:8093");
    playerEndpoints.put("Player-4", "http://localhost:8094");

    playerUcw.put("Player-1", new PlayerUcwIdentity());
    playerUcw.put("Player-2", new PlayerUcwIdentity());
    playerUcw.put("Player-3", new PlayerUcwIdentity());
    playerUcw.put("Player-4", new PlayerUcwIdentity());

    playerAgentIds.put("Player-1", "agent:player1@localhost:8091");
    playerAgentIds.put("Player-2", "agent:player2@localhost:8092");
    playerAgentIds.put("Player-3", "agent:player3@localhost:8093");
    playerAgentIds.put("Player-4", "agent:player4@localhost:8094");
  }

  public String getTransportMode() {
    return transportMode;
  }

  public void setTransportMode(String transportMode) {
    this.transportMode = transportMode;
  }

  public String getTableId() {
    return tableId;
  }

  public void setTableId(String tableId) {
    this.tableId = tableId;
  }

  public int getStartingStack() {
    return startingStack;
  }

  public void setStartingStack(int startingStack) {
    this.startingStack = startingStack;
  }

  public int getSmallBlind() {
    return smallBlind;
  }

  public void setSmallBlind(int smallBlind) {
    this.smallBlind = smallBlind;
  }

  public int getBigBlind() {
    return bigBlind;
  }

  public void setBigBlind(int bigBlind) {
    this.bigBlind = bigBlind;
  }

  public int getAnte() {
    return ante;
  }

  public void setAnte(int ante) {
    this.ante = ante;
  }

  public int getSpectatorDelayMillis() {
    return spectatorDelayMillis;
  }

  public void setSpectatorDelayMillis(int spectatorDelayMillis) {
    this.spectatorDelayMillis = spectatorDelayMillis;
  }

  public int getActionTimeoutMillis() {
    return actionTimeoutMillis;
  }

  public void setActionTimeoutMillis(int actionTimeoutMillis) {
    this.actionTimeoutMillis = actionTimeoutMillis;
  }

  public int getSeatCount() {
    return seatCount;
  }

  public void setSeatCount(int seatCount) {
    this.seatCount = seatCount;
  }

  public boolean isDemoVisibilityMode() {
    return demoVisibilityMode;
  }

  public void setDemoVisibilityMode(boolean demoVisibilityMode) {
    this.demoVisibilityMode = demoVisibilityMode;
  }

  public int getMaxHands() {
    return maxHands;
  }

  public void setMaxHands(int maxHands) {
    this.maxHands = maxHands;
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

  public String getBusinessProfile() {
    return businessProfile;
  }

  public void setBusinessProfile(String businessProfile) {
    this.businessProfile = businessProfile;
  }

  public String getLocalAgentId() {
    return localAgentId;
  }

  public void setLocalAgentId(String localAgentId) {
    this.localAgentId = localAgentId;
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

  public int getAcpPollIntervalMillis() {
    return acpPollIntervalMillis;
  }

  public void setAcpPollIntervalMillis(int acpPollIntervalMillis) {
    this.acpPollIntervalMillis = acpPollIntervalMillis;
  }

  public int getInviteTimeoutMillis() {
    return inviteTimeoutMillis;
  }

  public void setInviteTimeoutMillis(int inviteTimeoutMillis) {
    this.inviteTimeoutMillis = inviteTimeoutMillis;
  }

  public String getCorrelationIdPrefix() {
    return correlationIdPrefix;
  }

  public void setCorrelationIdPrefix(String correlationIdPrefix) {
    this.correlationIdPrefix = correlationIdPrefix;
  }

  public int getUcwPollIntervalMillis() {
    return ucwPollIntervalMillis;
  }

  public void setUcwPollIntervalMillis(int ucwPollIntervalMillis) {
    this.ucwPollIntervalMillis = ucwPollIntervalMillis;
  }

  public int getUcwInviteJoinTimeoutMillis() {
    return ucwInviteJoinTimeoutMillis;
  }

  public void setUcwInviteJoinTimeoutMillis(int ucwInviteJoinTimeoutMillis) {
    this.ucwInviteJoinTimeoutMillis = ucwInviteJoinTimeoutMillis;
  }

  public int getUcwClosureTimeoutMillis() {
    return ucwClosureTimeoutMillis;
  }

  public void setUcwClosureTimeoutMillis(int ucwClosureTimeoutMillis) {
    this.ucwClosureTimeoutMillis = ucwClosureTimeoutMillis;
  }

  public Map<String, String> getPlayerEndpoints() {
    return playerEndpoints;
  }

  public void setPlayerEndpoints(Map<String, String> playerEndpoints) {
    this.playerEndpoints = playerEndpoints;
  }

  public Map<String, String> getPlayerAgentIds() {
    return playerAgentIds;
  }

  public void setPlayerAgentIds(Map<String, String> playerAgentIds) {
    this.playerAgentIds = playerAgentIds;
  }

  public Map<String, PlayerUcwIdentity> getPlayerUcw() {
    return playerUcw;
  }

  public void setPlayerUcw(Map<String, PlayerUcwIdentity> playerUcw) {
    this.playerUcw = playerUcw;
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

  public static class PlayerUcwIdentity {
    private String participantUrn;
    private String userUrn;

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
  }
}
