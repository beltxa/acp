package com.cooperate.chessplayer.api;

import com.cooperate.chessplayer.service.AcpChessClient;
import com.cooperate.chessplayer.service.ChessMatchOrchestrator;
import org.acp.client.InboundResult;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class AcpController {
  private final AcpChessClient acpChessClient;
  private final ChessMatchOrchestrator orchestrator;

  public AcpController(AcpChessClient acpChessClient, ChessMatchOrchestrator orchestrator) {
    this.acpChessClient = acpChessClient;
    this.orchestrator = orchestrator;
  }

  @PostMapping("/api/v1/acp/messages")
  public ResponseEntity<InboundResult> receiveMessage(@RequestBody Map<String, Object> rawMessage) {
    InboundResult result = acpChessClient.receive(rawMessage);
    if (result != null && result.getDecryptedPayload() != null) {
      orchestrator.onInboundPayload(result.getDecryptedPayload());
    }
    return ResponseEntity.ok(result);
  }

  @GetMapping("/.well-known/acp")
  public ResponseEntity<Map<String, Object>> wellKnown() {
    return ResponseEntity.ok(acpChessClient.getWellKnownDocument());
  }

  @GetMapping("/api/v1/acp/identity")
  public ResponseEntity<Map<String, Object>> localIdentity() {
    return ResponseEntity.ok(Map.of("identity_document", acpChessClient.getIdentityDocument()));
  }
}
