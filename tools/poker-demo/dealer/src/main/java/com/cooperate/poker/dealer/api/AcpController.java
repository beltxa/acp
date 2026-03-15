package com.cooperate.poker.dealer.api;

import com.cooperate.poker.dealer.messaging.AcpDealerOutboundChannel;
import org.acp.client.InboundResult;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@ConditionalOnProperty(name = "poker.dealer.transport-mode", havingValue = "ACP")
public class AcpController {
  private final AcpDealerOutboundChannel acpChannel;

  public AcpController(AcpDealerOutboundChannel acpChannel) {
    this.acpChannel = acpChannel;
  }

  @PostMapping("/api/v1/acp/messages")
  public ResponseEntity<InboundResult> receiveMessage(@RequestBody Map<String, Object> rawMessage) {
    InboundResult result = acpChannel.receive(rawMessage);
    if (result != null && result.getDecryptedPayload() != null) {
      acpChannel.onInboundPayload(result.getDecryptedPayload());
    }
    return ResponseEntity.ok(result);
  }

  @GetMapping("/.well-known/acp")
  public ResponseEntity<Map<String, Object>> wellKnown() {
    return ResponseEntity.ok(acpChannel.getWellKnownDocument());
  }

  @GetMapping("/api/v1/acp/identity")
  public ResponseEntity<Map<String, Object>> localIdentity() {
    return ResponseEntity.ok(Map.of("identity_document", acpChannel.getIdentityDocument()));
  }
}
