package com.cooperate.poker.common.protocol;

import com.cooperate.poker.common.model.ActionType;
import com.cooperate.poker.common.model.MessageType;
import com.cooperate.poker.common.model.PlayerAction;
import com.cooperate.poker.common.model.RoundType;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class PokerPayloadCodecTest {

  private final ObjectMapper mapper = JsonMapper.builder().findAndAddModules().build();
  private final PokerPayloadCodec codec = new PokerPayloadCodec(mapper);

  @Test
  void encodesAndParsesEnvelopePayload() {
    ActionRequestMessage message = new ActionRequestMessage(
        MessageType.ACTION_REQUEST,
        "table-42",
        5,
        RoundType.TURN,
        "Player-2",
        List.of("Ah", "Kd"),
        List.of("2c", "7d", "Jh", "Qc"),
        240,
        40,
        40,
        960,
        40,
        List.of(ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
    );

    String payload = codec.encode(MessageType.ACTION_REQUEST, "table-42", 5, "Player-2", 9, message);
    PokerPayloadEvent event = codec.parse(payload).orElseThrow();
    ActionRequestMessage decoded = codec.payloadAs(event, ActionRequestMessage.class).orElseThrow();

    assertThat(event.profile()).isEqualTo(PokerPayloadCodec.PROFILE);
    assertThat(event.eventType()).isEqualTo("ACTION_REQUEST");
    assertThat(event.sequence()).isEqualTo(9);
    assertThat(event.tableId()).isEqualTo("table-42");
    assertThat(event.handNumber()).isEqualTo(5);
    assertThat(decoded).isEqualTo(message);
  }

  @Test
  void parsesLegacyPayloadShape() throws Exception {
    ActionResponseMessage message = new ActionResponseMessage(
        MessageType.ACTION_RESPONSE,
        "table-99",
        "Player-3",
        new PlayerAction(ActionType.CALL, 20, "legacy shape")
    );
    String legacyPayload = mapper.writeValueAsString(message);

    PokerPayloadEvent event = codec.parse(legacyPayload).orElseThrow();
    ActionResponseMessage decoded = codec.payloadAs(event, ActionResponseMessage.class).orElseThrow();

    assertThat(event.eventType()).isEqualTo("ACTION_RESPONSE");
    assertThat(event.sequence()).isEqualTo(0);
    assertThat(decoded).isEqualTo(message);
  }
}
