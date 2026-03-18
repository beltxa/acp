package com.cooperate.poker.dealer.api;

import com.cooperate.poker.dealer.service.DealerService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/dealer")
public class DealerControlController {
  private final DealerService dealerService;

  public DealerControlController(DealerService dealerService) {
    this.dealerService = dealerService;
  }

  @PostMapping("/start")
  public ResponseEntity<Map<String, String>> startGame() {
    dealerService.startGame();
    return ResponseEntity.accepted().body(Map.of("status", "starting"));
  }

  @PostMapping("/reset")
  public ResponseEntity<Map<String, String>> resetGame() {
    dealerService.resetGame();
    return ResponseEntity.ok(Map.of("status", "reset"));
  }
}
