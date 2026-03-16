import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { MqttTransportClient, metadataProperties } from "../src/mqttTransport.js";
import { JsonMap, toJsonMap } from "../src/jsonSupport.js";
import { parseAcpMessage } from "../src/messages.js";

const VECTORS_DIR = join(process.cwd(), "..", "tests", "vectors", "mqtt");

const REQUIRED_FIXTURES = [
  "python_to_python_send.json",
  "java_to_python_send.json",
  "python_to_java_send.json",
  "multi_recipient_send_B.json",
  "multi_recipient_send_C.json",
  "multi_recipient_send_D.json",
  "duplicate_delivery_case.json",
  "ack_example.json",
  "fail_example.json"
];

const STANDARD_FIXTURES = [
  "python_to_python_send.json",
  "java_to_python_send.json",
  "python_to_java_send.json",
  "multi_recipient_send_B.json",
  "multi_recipient_send_C.json",
  "multi_recipient_send_D.json",
  "ack_example.json",
  "fail_example.json"
];

function loadFixture(name: string): JsonMap {
  return JSON.parse(readFileSync(join(VECTORS_DIR, name), "utf-8")) as JsonMap;
}

describe("MQTT fixtures", () => {
  it.each(REQUIRED_FIXTURES)("required fixture exists: %s", (name) => {
    const fixture = loadFixture(name);
    expect(fixture).toBeTruthy();
  });

  it.each(STANDARD_FIXTURES)("standard fixture matches metadata conventions: %s", (name) => {
    const fixture = loadFixture(name);
    const body = toJsonMap(fixture.serialized_body);
    parseAcpMessage(body);
    const envelope = toJsonMap(body.envelope);
    const recipients = envelope.recipients as unknown[];
    expect(Array.isArray(recipients)).toBe(true);
    expect(recipients.length).toBe(1);
    const recipient = String(recipients[0]);
    const transport = toJsonMap(fixture.transport_metadata);
    expect(transport.topic).toBe(MqttTransportClient.topicForAgent(recipient));
    expect(Number(transport.qos)).toBe(1);
    expect(toJsonMap(transport.user_properties)).toEqual(metadataProperties(body));
  });

  it("duplicate fixture keeps same message_id", () => {
    const fixture = loadFixture("duplicate_delivery_case.json");
    const original = toJsonMap(toJsonMap(fixture.original_message).serialized_body);
    const duplicate = toJsonMap(toJsonMap(fixture.duplicate_message).serialized_body);
    const originalEnvelope = toJsonMap(original.envelope);
    const duplicateEnvelope = toJsonMap(duplicate.envelope);
    expect(originalEnvelope.message_id).toBe(duplicateEnvelope.message_id);
  });
});
