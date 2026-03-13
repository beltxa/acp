package com.cooperate.chessplayer.config;

import com.cooperate.chessplayer.model.ChessColor;
import com.cooperate.chessplayer.model.PlayerRole;
import com.cooperate.chessplayer.model.ReasoningEffort;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.Locale;

@ConfigurationProperties(prefix = "cooperate.chess")
public class ChessPlayerProperties {
  private PlayerRole role = PlayerRole.INITIATOR;
  private ChessColor color = ChessColor.WHITE;
  private String localAgentId = "agent:player1@localhost:8088";
  private String remoteAgentId = "agent:player2@localhost:8089";
  private String localDisplayName = "Player 1 AI";
  private String remoteDisplayName = "Player 2 AI";
  private String publicBaseUrl = "http://localhost:8088";
  private String acpMessagePath = "/api/v1/acp/messages";
  private String acpStorageDir = "/var/lib/chess-agent/acp";
  private String acpDiscoveryScheme = "http";
  private String acpRelayUrl;
  private String acpDeliveryMode = "direct";
  private long pollIntervalMs = 2000L;
  private long moveSendDelayMs = 2000L;
  private long matchTimeoutSeconds = 1800L;
  private int maxPlies = 160;
  private boolean pgnExportEnabled = true;
  private String pgnExportDir = "/var/lib/chess-agent/pgn";
  private String stateFile = "/var/lib/chess-agent/state/matches.json";
  private String reducedMotion = "reduced";
  private ReasoningEffort reasoningEffort = ReasoningEffort.MEDIUM;
  private String openaiApiKey;
  private String openaiModel = "o3-mini";

  public PlayerRole getRole() {
    return role;
  }

  public void setRole(PlayerRole role) {
    this.role = role;
  }

  public ChessColor getColor() {
    return color;
  }

  public void setColor(ChessColor color) {
    this.color = color;
  }

  public String getLocalAgentId() {
    return localAgentId;
  }

  public void setLocalAgentId(String localAgentId) {
    this.localAgentId = localAgentId;
  }

  public String getRemoteAgentId() {
    return remoteAgentId;
  }

  public void setRemoteAgentId(String remoteAgentId) {
    this.remoteAgentId = remoteAgentId;
  }

  public String getLocalDisplayName() {
    return localDisplayName;
  }

  public void setLocalDisplayName(String localDisplayName) {
    this.localDisplayName = localDisplayName;
  }

  public String getRemoteDisplayName() {
    return remoteDisplayName;
  }

  public void setRemoteDisplayName(String remoteDisplayName) {
    this.remoteDisplayName = remoteDisplayName;
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

  public String getAcpDeliveryMode() {
    return acpDeliveryMode;
  }

  public void setAcpDeliveryMode(String acpDeliveryMode) {
    this.acpDeliveryMode = acpDeliveryMode;
  }

  public long getPollIntervalMs() {
    return pollIntervalMs;
  }

  public void setPollIntervalMs(long pollIntervalMs) {
    this.pollIntervalMs = pollIntervalMs;
  }

  public long getMoveSendDelayMs() {
    return moveSendDelayMs;
  }

  public void setMoveSendDelayMs(long moveSendDelayMs) {
    this.moveSendDelayMs = moveSendDelayMs;
  }

  public long getMatchTimeoutSeconds() {
    return matchTimeoutSeconds;
  }

  public void setMatchTimeoutSeconds(long matchTimeoutSeconds) {
    this.matchTimeoutSeconds = matchTimeoutSeconds;
  }

  public int getMaxPlies() {
    return maxPlies;
  }

  public void setMaxPlies(int maxPlies) {
    this.maxPlies = maxPlies;
  }

  public boolean isPgnExportEnabled() {
    return pgnExportEnabled;
  }

  public void setPgnExportEnabled(boolean pgnExportEnabled) {
    this.pgnExportEnabled = pgnExportEnabled;
  }

  public String getPgnExportDir() {
    return pgnExportDir;
  }

  public void setPgnExportDir(String pgnExportDir) {
    this.pgnExportDir = pgnExportDir;
  }

  public String getStateFile() {
    return stateFile;
  }

  public void setStateFile(String stateFile) {
    this.stateFile = stateFile;
  }

  public String getReducedMotion() {
    if (reducedMotion == null) {
      return "reduced";
    }
    String normalized = reducedMotion.trim().toLowerCase(Locale.ROOT);
    return switch (normalized) {
      case "off", "reduced", "system" -> normalized;
      default -> "reduced";
    };
  }

  public void setReducedMotion(String reducedMotion) {
    this.reducedMotion = reducedMotion;
  }

  public ReasoningEffort getReasoningEffort() {
    return reasoningEffort;
  }

  public void setReasoningEffort(ReasoningEffort reasoningEffort) {
    this.reasoningEffort = reasoningEffort;
  }

  public String getOpenaiApiKey() {
    return openaiApiKey;
  }

  public void setOpenaiApiKey(String openaiApiKey) {
    this.openaiApiKey = openaiApiKey;
  }

  public String getOpenaiModel() {
    return openaiModel;
  }

  public void setOpenaiModel(String openaiModel) {
    this.openaiModel = openaiModel;
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
