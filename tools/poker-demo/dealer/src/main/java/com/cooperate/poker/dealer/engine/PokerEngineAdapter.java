package com.cooperate.poker.dealer.engine;

import org.dsaw.poker.engine.Card;
import org.dsaw.poker.engine.Hand;
import org.dsaw.poker.engine.HandEvaluator;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Component
public class PokerEngineAdapter {

  public HandEvaluation evaluateHand(String playerId, List<String> holeCards, List<String> communityCards) {
    Hand hand = new Hand();
    for (String holeCard : holeCards) {
      hand.addCard(new Card(normalizeCard(holeCard)));
    }
    for (String communityCard : communityCards) {
      hand.addCard(new Card(normalizeCard(communityCard)));
    }

    HandEvaluator evaluator = new HandEvaluator(hand);
    String category = evaluator.getType().name();
    return new HandEvaluation(playerId, evaluator.getValue(), category);
  }

  public ShowdownResult resolveWinners(Map<String, List<String>> holeCardsByPlayer, List<String> communityCards) {
    if (holeCardsByPlayer == null || holeCardsByPlayer.isEmpty()) {
      return new ShowdownResult(List.of(), "NONE", Map.of());
    }

    List<HandEvaluation> evaluations = new ArrayList<>();
    for (Map.Entry<String, List<String>> entry : holeCardsByPlayer.entrySet()) {
      evaluations.add(evaluateHand(entry.getKey(), entry.getValue(), communityCards));
    }

    int best = evaluations.stream().mapToInt(HandEvaluation::score).max().orElse(Integer.MIN_VALUE);
    List<String> winners = evaluations.stream()
        .filter(v -> v.score() == best)
        .map(HandEvaluation::playerId)
        .toList();

    Map<String, Integer> scoreByPlayer = new LinkedHashMap<>();
    for (HandEvaluation evaluation : evaluations) {
      scoreByPlayer.put(evaluation.playerId(), evaluation.score());
    }

    String category = evaluations.stream()
        .filter(v -> winners.contains(v.playerId()))
        .findFirst()
        .map(HandEvaluation::category)
        .orElse("HIGH_CARD");

    return new ShowdownResult(winners, category, scoreByPlayer);
  }

  public Map<String, Integer> distributePot(List<String> winners, int pot) {
    if (winners == null || winners.isEmpty() || pot <= 0) {
      return Map.of();
    }

    int base = pot / winners.size();
    int remainder = pot % winners.size();

    Map<String, Integer> payouts = new LinkedHashMap<>();
    for (int i = 0; i < winners.size(); i++) {
      int amount = base + (i < remainder ? 1 : 0);
      payouts.put(winners.get(i), amount);
    }
    return payouts;
  }

  private String normalizeCard(String card) {
    if (card == null || card.length() != 2) {
      throw new IllegalArgumentException("Card must be in poker-engine format, e.g. As, Td");
    }
    String rank = card.substring(0, 1).toUpperCase(Locale.ROOT);
    String suit = card.substring(1, 2).toLowerCase(Locale.ROOT);
    return rank + suit;
  }

  public record HandEvaluation(String playerId, int score, String category) {
  }

  public record ShowdownResult(List<String> winnerIds, String handCategory, Map<String, Integer> scoreByPlayer) {
  }
}
