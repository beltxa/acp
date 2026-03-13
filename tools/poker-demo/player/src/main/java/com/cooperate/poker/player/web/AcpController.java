package com.cooperate.poker.player.web;

import com.cooperate.poker.player.service.AcpPlayerRuntime;
import org.acp.client.AgentIdentity;
import org.acp.client.InboundResult;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@ConditionalOnProperty(name = "poker.player.transport-mode", havingValue = "ACP")
public class AcpController {
  private final AcpPlayerRuntime acpPlayerRuntime;

  public AcpController(AcpPlayerRuntime acpPlayerRuntime) {
    this.acpPlayerRuntime = acpPlayerRuntime;
  }

  @PostMapping("/api/v1/acp/messages")
  public ResponseEntity<InboundResult> receiveMessage(@RequestBody Map<String, Object> rawMessage) {
    InboundResult result = acpPlayerRuntime.receive(rawMessage);
    if (result != null && result.getDecryptedPayload() != null) {
      acpPlayerRuntime.onInboundPayload(result.getDecryptedPayload());
    }
    return ResponseEntity.ok(result);
  }

  @GetMapping("/.well-known/acp/agents/{name}")
  public ResponseEntity<Map<String, Object>> identityDocument(@PathVariable("name") String name) {
    AgentIdentity.AgentIdParts parts = AgentIdentity.parseAgentId(acpPlayerRuntime.getLocalAgentId());
    if (!parts.name().equals(name)) {
      return ResponseEntity.notFound().build();
    }
    return ResponseEntity.ok(Map.of("identity_document", acpPlayerRuntime.getIdentityDocument()));
  }

  @GetMapping("/api/v1/acp/identity")
  public ResponseEntity<Map<String, Object>> localIdentity() {
    return ResponseEntity.ok(Map.of("identity_document", acpPlayerRuntime.getIdentityDocument()));
  }
}
