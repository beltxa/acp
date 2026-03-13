package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.GameState;
import com.cooperate.poker.common.model.GameStatus;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.PlayerState;
import com.cooperate.poker.common.model.PlayerStatus;
import com.cooperate.poker.common.model.RoundType;
import com.cooperate.poker.common.model.SeatState;
import com.cooperate.poker.common.model.TableState;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class ProtocolSerializationTest {

  private final ObjectMapper mapper = JsonMapper.builder().findAndAddModules().build();

  @Test
  void serializesAndDeserializesActionRequest() throws Exception {
    ActionRequestMessage original = new ActionRequestMessage(
        MessageType.ACTION_REQUEST,
        "table-1",
        3,
        RoundType.TURN,
        "Player-1",
        List.of("Ah", "Kd"),
        List.of("7h", "8d", "9c", "2s"),
        120,
        20,
        20,
        950,
        20,
        List.of(ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
    );

    String json = mapper.writeValueAsString(original);
    ActionRequestMessage roundTrip = mapper.readValue(json, ActionRequestMessage.class);

    assertThat(roundTrip).isEqualTo(original);
  }

  @Test
  void serializesAndDeserializesTableState() throws Exception {
    PlayerState player = new PlayerState(
        "Player-1",
        990,
        PlayerStatus.ACTIVE,
        List.of("As", "Kd"),
        10,
        -10,
        -10,
        new PlayerAction(ActionType.CALL, 10, "defend blind")
    );
    GameState gameState = new GameState(
        "table-1",
        1,
        RoundType.PRE_FLOP,
        List.of(),
        Map.of("Player-1", player),
        15,
        10,
        10,
        "Player-2",
        GameStatus.IN_PROGRESS
    );
    TableState original = new TableState(
        "table-1",
        GameStatus.IN_PROGRESS,
        List.of(new SeatState(1, "Player-1", true)),
        gameState,
        List.of("hand started"),
        List.of("Player-1: conservative call")
    );

    String json = mapper.writeValueAsString(original);
    TableState roundTrip = mapper.readValue(json, TableState.class);

    assertThat(roundTrip).isEqualTo(original);
  }
}
