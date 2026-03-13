package com.cooperate.chessplayer.service;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import com.cooperate.chessplayer.model.MatchState;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Component
public class MatchStateStore {
  private static final Logger log = LoggerFactory.getLogger(MatchStateStore.class);

  private final Object lock = new Object();
  private final ObjectMapper objectMapper;
  private final ChessPlayerProperties properties;
  private final MatchUpdateBroadcaster updateBroadcaster;
  private final Map<UUID, MatchState> byUcwId = new LinkedHashMap<>();

  public MatchStateStore(
      ObjectMapper objectMapper,
      ChessPlayerProperties properties,
      MatchUpdateBroadcaster updateBroadcaster
  ) {
    this.objectMapper = objectMapper;
    this.properties = properties;
    this.updateBroadcaster = updateBroadcaster;
  }

  @PostConstruct
  public void load() {
    synchronized (lock) {
      Path statePath = Path.of(properties.getStateFile());
      if (!Files.exists(statePath)) {
        return;
      }
      try {
        StateEnvelope envelope = objectMapper.readValue(Files.readString(statePath), StateEnvelope.class);
        byUcwId.clear();
        if (envelope != null && envelope.matches != null) {
          for (MatchState state : envelope.matches) {
            if (state != null && state.getUcwId() != null) {
              byUcwId.put(state.getUcwId(), state);
            }
          }
        }
        log.info("Loaded {} chess match states from {}", byUcwId.size(), statePath);
      } catch (Exception e) {
        log.warn("Failed to load chess match state from {}", statePath, e);
      }
    }
  }

  public List<MatchState> list() {
    synchronized (lock) {
      return byUcwId.values().stream()
          .sorted(Comparator.comparing(MatchState::getCreatedAt, Comparator.nullsLast(Comparator.naturalOrder())))
          .map(this::copy)
          .toList();
    }
  }

  public Optional<MatchState> find(UUID ucwId) {
    synchronized (lock) {
      MatchState state = byUcwId.get(ucwId);
      return state == null ? Optional.empty() : Optional.of(copy(state));
    }
  }

  public void upsert(MatchState state) {
    synchronized (lock) {
      if (state == null || state.getUcwId() == null) {
        return;
      }
      MatchState next = copy(state);
      MatchState current = byUcwId.get(state.getUcwId());
      if (current != null && equivalentIgnoringUpdatedAt(current, next)) {
        return;
      }
      next.setUpdatedAt(Instant.now());
      byUcwId.put(next.getUcwId(), next);
      persist();
      updateBroadcaster.publish(next.getUcwId());
    }
  }

  public void remove(UUID ucwId) {
    synchronized (lock) {
      MatchState removed = byUcwId.remove(ucwId);
      if (removed == null) {
        return;
      }
      persist();
      updateBroadcaster.publish(ucwId);
    }
  }

  private void persist() {
    Path statePath = Path.of(properties.getStateFile());
    try {
      Files.createDirectories(statePath.getParent());
      StateEnvelope envelope = new StateEnvelope();
      envelope.generatedAt = Instant.now();
      envelope.matches = new ArrayList<>(byUcwId.values());
      String json = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(envelope);
      Files.writeString(
          statePath,
          json,
          StandardOpenOption.CREATE,
          StandardOpenOption.TRUNCATE_EXISTING,
          StandardOpenOption.WRITE
      );
    } catch (Exception e) {
      log.warn("Failed to persist chess match state to {}", statePath, e);
    }
  }

  private MatchState copy(MatchState source) {
    try {
      return objectMapper.readValue(objectMapper.writeValueAsBytes(source), MatchState.class);
    } catch (Exception e) {
      throw new IllegalStateException("Failed to clone match state", e);
    }
  }

  private boolean equivalentIgnoringUpdatedAt(MatchState left, MatchState right) {
    MatchState leftCopy = copy(left);
    MatchState rightCopy = copy(right);
    leftCopy.setUpdatedAt(null);
    rightCopy.setUpdatedAt(null);
    try {
      String leftJson = objectMapper.writeValueAsString(leftCopy);
      String rightJson = objectMapper.writeValueAsString(rightCopy);
      return leftJson.equals(rightJson);
    } catch (Exception e) {
      throw new IllegalStateException("Failed to compare match states", e);
    }
  }

  public static class StateEnvelope {
    @JsonProperty("generated_at")
    public Instant generatedAt;

    @JsonProperty("matches")
    public List<MatchState> matches = List.of();
  }
}
