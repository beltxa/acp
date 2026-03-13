package com.cooperate.chessplayer.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class MatchState {
  private UUID ucwId;
  private UUID matchId;
  private ChessColor localColor;
  private String localParticipantUrn;
  private String remoteParticipantUrn;
  private String localUserUrn;
  private String remoteUserUrn;
  private ReasoningEffort reasoningEffort = ReasoningEffort.MEDIUM;
  private String currentFen;
  private int latestSequence;
  private List<String> moveHistoryUci = new ArrayList<>();
  private String ucwStatus;
  private MatchStateStatus status = MatchStateStatus.INVITED;
  private GameOutcome outcome = GameOutcome.ONGOING;
  private String outcomeReason;
  private boolean completionProposalSent;
  private boolean completionResponseSent;
  private boolean pgnExported;
  private Instant createdAt;
  private Instant updatedAt;
  private Instant lastActionAt;

  public UUID getUcwId() {
    return ucwId;
  }

  public void setUcwId(UUID ucwId) {
    this.ucwId = ucwId;
  }

  public UUID getMatchId() {
    return matchId;
  }

  public void setMatchId(UUID matchId) {
    this.matchId = matchId;
  }

  public ChessColor getLocalColor() {
    return localColor;
  }

  public void setLocalColor(ChessColor localColor) {
    this.localColor = localColor;
  }

  public String getLocalParticipantUrn() {
    return localParticipantUrn;
  }

  public void setLocalParticipantUrn(String localParticipantUrn) {
    this.localParticipantUrn = localParticipantUrn;
  }

  public String getRemoteParticipantUrn() {
    return remoteParticipantUrn;
  }

  public void setRemoteParticipantUrn(String remoteParticipantUrn) {
    this.remoteParticipantUrn = remoteParticipantUrn;
  }

  public String getLocalUserUrn() {
    return localUserUrn;
  }

  public void setLocalUserUrn(String localUserUrn) {
    this.localUserUrn = localUserUrn;
  }

  public String getRemoteUserUrn() {
    return remoteUserUrn;
  }

  public void setRemoteUserUrn(String remoteUserUrn) {
    this.remoteUserUrn = remoteUserUrn;
  }

  public ReasoningEffort getReasoningEffort() {
    return reasoningEffort;
  }

  public void setReasoningEffort(ReasoningEffort reasoningEffort) {
    this.reasoningEffort = reasoningEffort;
  }

  public String getCurrentFen() {
    return currentFen;
  }

  public void setCurrentFen(String currentFen) {
    this.currentFen = currentFen;
  }

  public int getLatestSequence() {
    return latestSequence;
  }

  public void setLatestSequence(int latestSequence) {
    this.latestSequence = latestSequence;
  }

  public List<String> getMoveHistoryUci() {
    return moveHistoryUci;
  }

  public void setMoveHistoryUci(List<String> moveHistoryUci) {
    this.moveHistoryUci = moveHistoryUci;
  }

  public String getUcwStatus() {
    return ucwStatus;
  }

  public void setUcwStatus(String ucwStatus) {
    this.ucwStatus = ucwStatus;
  }

  public MatchStateStatus getStatus() {
    return status;
  }

  public void setStatus(MatchStateStatus status) {
    this.status = status;
  }

  public GameOutcome getOutcome() {
    return outcome;
  }

  public void setOutcome(GameOutcome outcome) {
    this.outcome = outcome;
  }

  public String getOutcomeReason() {
    return outcomeReason;
  }

  public void setOutcomeReason(String outcomeReason) {
    this.outcomeReason = outcomeReason;
  }

  public boolean isCompletionProposalSent() {
    return completionProposalSent;
  }

  public void setCompletionProposalSent(boolean completionProposalSent) {
    this.completionProposalSent = completionProposalSent;
  }

  public boolean isCompletionResponseSent() {
    return completionResponseSent;
  }

  public void setCompletionResponseSent(boolean completionResponseSent) {
    this.completionResponseSent = completionResponseSent;
  }

  public boolean isPgnExported() {
    return pgnExported;
  }

  public void setPgnExported(boolean pgnExported) {
    this.pgnExported = pgnExported;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }

  public Instant getLastActionAt() {
    return lastActionAt;
  }

  public void setLastActionAt(Instant lastActionAt) {
    this.lastActionAt = lastActionAt;
  }
}
