import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { AmqpTransportClient } from "../src/amqpTransport.js";
import { JsonMap, toJsonMap } from "../src/jsonSupport.js";
import { parseAcpMessage } from "../src/messages.js";

const VECTORS_DIR = join(process.cwd(), "..", "tests", "vectors", "amqp");

const REQUIRED_FIXTURES = [
  "python_to_python_send.json",
  "java_to_python_send.json",
  "python_to_java_send.json",
  "multi_recipient_send_B.json",
  "multi_recipient_send_C.json",
  "multi_recipient_send_D.json",
  "duplicate_delivery_case.json",
  "relay_amqp_fallback_case.json",
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

describe("AMQP fixtures", () => {
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
    const headers = toJsonMap(transport.headers);
    expect(headers.acp_version).toBe(envelope.acp_version);
    expect(headers.acp_message_class).toBe(envelope.message_class);
    expect(headers.acp_message_id).toBe(envelope.message_id);
    expect(headers.acp_operation_id).toBe(envelope.operation_id);
    expect(headers.acp_sender).toBe(envelope.sender);
    expect(transport.routing_key).toBe(AmqpTransportClient.routingKeyForAgent(recipient));
    expect(transport.queue).toBe(AmqpTransportClient.queueNameForAgent(recipient));
  });

  it("duplicate fixture keeps same message_id", () => {
    const fixture = loadFixture("duplicate_delivery_case.json");
    const original = toJsonMap(toJsonMap(fixture.original_message).serialized_body);
    const duplicate = toJsonMap(toJsonMap(fixture.duplicate_message).serialized_body);
    const originalEnvelope = toJsonMap(original.envelope);
    const duplicateEnvelope = toJsonMap(duplicate.envelope);
    expect(originalEnvelope.message_id).toBe(duplicateEnvelope.message_id);
  });

  it("relay fallback fixture preserves serialized body", () => {
    const fixture = loadFixture("relay_amqp_fallback_case.json");
    const input = toJsonMap(toJsonMap(fixture.input_acp_message).serialized_body);
    const emitted = toJsonMap(toJsonMap(fixture.emitted_amqp_message).serialized_body);
    expect(input).toEqual(emitted);
  });
});
