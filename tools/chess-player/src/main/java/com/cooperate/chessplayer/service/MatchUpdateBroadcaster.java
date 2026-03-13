package com.cooperate.chessplayer.service;

import org.springframework.stereotype.Component;

import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

@Component
public class MatchUpdateBroadcaster {
  private final CopyOnWriteArrayList<Consumer<UUID>> listeners = new CopyOnWriteArrayList<>();

  public Runnable register(Consumer<UUID> listener) {
    listeners.add(listener);
    return () -> listeners.remove(listener);
  }

  public void publish(UUID ucwId) {
    for (Consumer<UUID> listener : listeners) {
      try {
        listener.accept(ucwId);
      } catch (RuntimeException ignored) {
      }
    }
  }
}
