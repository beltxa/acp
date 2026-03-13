package com.cooperate.poker.dealer.engine;

import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;

@Service
public class DeckService {
  private static final List<String> RANKS = List.of("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A");
  private static final List<String> SUITS = List.of("c", "d", "h", "s");

  private final SecureRandom random = new SecureRandom();

  public List<String> createDeck() {
    List<String> cards = new ArrayList<>(52);
    for (String rank : RANKS) {
      for (String suit : SUITS) {
        cards.add(rank + suit);
      }
    }
    return cards;
  }

  public Deque<String> shuffle() {
    List<String> cards = createDeck();
    Collections.shuffle(cards, random);
    return new ArrayDeque<>(cards);
  }

  public String dealCard(Deque<String> deck) {
    if (deck == null || deck.isEmpty()) {
      throw new IllegalStateException("Deck is empty");
    }
    return deck.removeFirst();
  }
}
