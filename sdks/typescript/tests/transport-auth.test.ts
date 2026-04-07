import { describe, expect, it } from "vitest";
import { AmqpTransportClient } from "../src/amqpTransport.js";
import { MqttTransportClient } from "../src/mqttTransport.js";
import { defaultAgentOptions, optionsFromConfigMap, optionsToConfigMap } from "../src/options.js";
import { httpAuthHeaders, parseAuthConfig } from "../src/transportAuth.js";

describe("Transport auth", () => {
  it("builds bearer authorization headers", () => {
    const auth = parseAuthConfig({
      type: "bearer",
      parameters: { token: "demo-token" }
    });
    expect(httpAuthHeaders(auth)).toEqual({ Authorization: "Bearer demo-token" });
  });

  it("embeds auth config in AMQP service hints", () => {
    const hint = AmqpTransportClient.buildServiceHint(
      "agent:sender@demo",
      "amqps://broker.local",
      "acp.exchange",
      {
        type: "username_password",
        parameters: { username: "agentA", password: "secret" }
      }
    );
    expect((hint.auth as { type: string }).type).toBe("username_password");
  });

  it("embeds auth config in MQTT service hints", () => {
    const hint = MqttTransportClient.buildServiceHint(
      "agent:sender@demo",
      "mqtts://broker.local:8883",
      undefined,
      1,
      "acp/agent",
      {
        type: "username_password",
        parameters: { username: "agentA", password: "secret" }
      }
    );
    expect((hint.auth as { type: string }).type).toBe("username_password");
  });

  it("parses direct and relay transport auth from options config map", () => {
    const options = optionsFromConfigMap({
      direct_transport_auth: {
        type: "bearer",
        parameters: { token: "direct-token" }
      },
      relay_transport_auth: {
        type: "bearer",
        parameters: { token: "relay-token" }
      }
    });
    expect(options.direct_transport_auth?.type).toBe("bearer");
    expect(options.relay_transport_auth?.parameters.token).toBe("relay-token");
  });

  it("serializes broker auth in options config map", () => {
    const exported = optionsToConfigMap({
      ...defaultAgentOptions(),
      amqp_auth: {
        type: "username_password",
        parameters: { username: "agentA", password: "secret" }
      },
      mqtt_auth: {
        type: "username_password",
        parameters: { username: "agentA", password: "secret" }
      }
    });
    expect((exported.amqp_auth as { type: string }).type).toBe("username_password");
    expect((exported.mqtt_auth as { type: string }).type).toBe("username_password");
  });
});
