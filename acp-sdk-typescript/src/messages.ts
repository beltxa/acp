import { randomUUID } from "node:crypto";
import { ACP_VERSION, DEFAULT_CRYPTO_SUITE } from "./constants.js";
import { JsonMap, JsonValue, toJsonMap } from "./jsonSupport.js";
import { validationError } from "./errors.js";

export type MessageClass = "SEND" | "ACK" | "FAIL" | "CAPABILITIES" | "COMPENSATE";
export type DeliveryState =
  | "PENDING"
  | "DELIVERED"
  | "ACKNOWLEDGED"
  | "FAILED"
  | "DECLINED"
  | "EXPIRED";
export type DeliveryMode = "auto" | "direct" | "relay" | "amqp" | "mqtt";

export interface WrappedContentKey {
  recipient: string;
  ephemeral_public_key: string;
  nonce: string;
  ciphertext: string;
}

export interface Envelope {
  acp_version: string;
  message_class: MessageClass;
  message_id: string;
  operation_id: string;
  timestamp: string;
  expires_at: string;
  sender: string;
  recipients: string[];
  context_id: string;
  crypto_suite: string;
  correlation_id?: string;
  in_reply_to?: string;
}

export interface ProtectedPayload {
  nonce: string;
  ciphertext: string;
  wrapped_content_keys: WrappedContentKey[];
  payload_hash: string;
  signature_kid: string;
  signature: string;
}

export interface AcpMessage {
  envelope: Envelope;
  protected: ProtectedPayload;
  sender_identity_document?: JsonMap;
}

export interface DeliveryOutcome {
  recipient: string;
  state: DeliveryState;
  status_code?: number;
  response_class?: MessageClass;
  reason_code?: string;
  detail?: string;
  response_message?: JsonMap;
}

export interface SendResult {
  operation_id: string;
  message_id: string;
  message_ids: string[];
  outcomes: DeliveryOutcome[];
}

export interface CompensateInstruction {
  operation_id: string;
  reason: string;
  actions: JsonMap[];
}

export function parseMessageClass(value: string | undefined): MessageClass | undefined {
  if (!value) {
    return undefined;
  }
  if (
    value === "SEND" ||
    value === "ACK" ||
    value === "FAIL" ||
    value === "CAPABILITIES" ||
    value === "COMPENSATE"
  ) {
    return value;
  }
  return undefined;
}

export function buildEnvelope(input: {
  sender: string;
  recipients: string[];
  message_class: MessageClass;
  context_id: string;
  expires_in_seconds: number;
  operation_id?: string;
  correlation_id?: string;
  in_reply_to?: string;
  crypto_suite?: string;
}): Envelope {
  const now = new Date();
  const expires = new Date(now.getTime() + Math.max(1, input.expires_in_seconds) * 1000);
  const envelope: Envelope = {
    acp_version: ACP_VERSION,
    message_class: input.message_class,
    message_id: randomUUID(),
    operation_id: input.operation_id ?? randomUUID(),
    timestamp: now.toISOString(),
    expires_at: expires.toISOString(),
    sender: input.sender,
    recipients: input.recipients,
    context_id: input.context_id,
    crypto_suite: input.crypto_suite ?? DEFAULT_CRYPTO_SUITE
  };
  if (input.correlation_id) {
    envelope.correlation_id = input.correlation_id;
  }
  if (input.in_reply_to) {
    envelope.in_reply_to = input.in_reply_to;
  }
  validateEnvelope(envelope);
  return envelope;
}

export function validateEnvelope(envelope: Envelope): void {
  if (!envelope.sender.trim()) {
    throw validationError("Envelope sender is required");
  }
  if (!Array.isArray(envelope.recipients) || envelope.recipients.length === 0) {
    throw validationError("Envelope recipients must not be empty");
  }
  const timestamp = Date.parse(envelope.timestamp);
  const expires = Date.parse(envelope.expires_at);
  if (Number.isNaN(timestamp) || Number.isNaN(expires)) {
    throw validationError("Envelope timestamps must be RFC3339 strings");
  }
  if (expires <= timestamp) {
    throw validationError("Envelope expires_at must be after timestamp");
  }
}

export function isExpired(envelope: Envelope): boolean {
  const expires = Date.parse(envelope.expires_at);
  return Number.isNaN(expires) || expires <= Date.now();
}

export function parseAcpMessage(map: JsonMap): AcpMessage {
  const envelope = toJsonMap(map.envelope) as unknown as Envelope;
  const protectedPayload = toJsonMap(map.protected) as unknown as ProtectedPayload;
  const message: AcpMessage = {
    envelope,
    protected: protectedPayload
  };
  if (map.sender_identity_document !== undefined && map.sender_identity_document !== null) {
    message.sender_identity_document = toJsonMap(map.sender_identity_document);
  }
  validateEnvelope(envelope);
  return message;
}

export function messageToMap(message: AcpMessage): JsonMap {
  const output: JsonMap = {
    envelope: message.envelope as unknown as JsonValue,
    protected: message.protected as unknown as JsonValue
  };
  if (message.sender_identity_document) {
    output.sender_identity_document = message.sender_identity_document;
  }
  return output;
}

export function buildAckPayload(receivedMessageId: string, status: string): JsonMap {
  return {
    status,
    received_message_id: receivedMessageId
  };
}

export function buildFailPayload(reasonCode: string, detail: string, retriable: boolean): JsonMap {
  return {
    reason_code: reasonCode,
    detail,
    retriable
  };
}
