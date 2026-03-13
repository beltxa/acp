package com.cooperate.poker.dealer.engine;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class DeckServiceTest {

  private final DeckService deckService = new DeckService();

  @Test
  void createDeckProduces52UniqueCards() {
    var deck = deckService.createDeck();
    assertThat(deck).hasSize(52);

    Set<String> unique = new HashSet<>(deck);
    assertThat(unique).hasSize(52);
    assertThat(deck).contains("As", "Td", "2c", "Kh");
  }

  @Test
  void dealCardRemovesCardFromDeck() {
    var deck = deckService.shuffle();

    String first = deckService.dealCard(deck);

    assertThat(first).isNotBlank();
    assertThat(deck).hasSize(51);
    assertThat(deck).doesNotContain(first);
  }
}
