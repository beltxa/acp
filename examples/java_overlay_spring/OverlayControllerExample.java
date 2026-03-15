package com.example.overlay;

import org.acp.client.AcpAgent;
import org.acp.client.AcpAgentOptions;
import org.acp.client.DeliveryMode;
import org.acp.client.framework.OverlayHttpRuntime;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Path;
import java.util.Map;

@RestController
public class OverlayControllerExample {
    private final OverlayHttpRuntime overlay;

    public OverlayControllerExample() {
        AcpAgent agent = AcpAgent.loadOrCreate(
            "agent:orders.service@localhost:9090",
            new AcpAgentOptions()
                .setStorageDir(Path.of(".acp-data-overlay-spring"))
                .setEndpoint("http://localhost:9090/orders")
                .setDiscoveryScheme("http")
                .setAllowInsecureHttp(true)
        );
        this.overlay = new OverlayHttpRuntime(
            agent,
            "http://localhost:9090",
            payload -> Map.of("accepted", true, "echo", payload),
            body -> Map.of("accepted", true, "echo", body)
        );
    }

    @PostMapping("/api/v1/acp/messages")
    public ResponseEntity<Map<String, Object>> inbound(@RequestBody Map<String, Object> rawMessage) {
        OverlayHttpRuntime.HttpOverlayResponse response = overlay.handleMessageBody(rawMessage);
        return ResponseEntity.status(response.statusCode()).body(response.body());
    }

    @GetMapping("/.well-known/acp")
    public ResponseEntity<Map<String, Object>> wellKnown() {
        return ResponseEntity.ok(overlay.wellKnownDocument());
    }

    @GetMapping("/api/v1/acp/identity")
    public ResponseEntity<Map<String, Object>> identity() {
        return ResponseEntity.ok(overlay.identityDocumentPayload());
    }

    @PostMapping("/orders/send")
    public ResponseEntity<Map<String, Object>> sendOrder(
        @RequestParam("target") String targetBaseUrl,
        @RequestBody Map<String, Object> payload
    ) {
        Map<String, Object> result = overlay.sendBusinessPayload(
            payload,
            targetBaseUrl,
            null,
            "overlay:spring:orders",
            DeliveryMode.AUTO,
            300
        );
        return ResponseEntity.ok(result);
    }
}
