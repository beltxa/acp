package com.cooperate.poker.dealer.service;

import com.cooperate.poker.common.model.TableState;
import org.springframework.stereotype.Repository;

import java.util.concurrent.atomic.AtomicReference;

@Repository
public class TableStateRepository {
  private final AtomicReference<TableState> state = new AtomicReference<>();

  public void save(TableState tableState) {
    state.set(tableState);
  }

  public TableState get() {
    return state.get();
  }
}
