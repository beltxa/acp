import { validationError } from "./errors.js";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonMap = Record<string, JsonValue>;

function normalizeJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeJson(item));
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  const output: JsonMap = {};
  const keys = Object.keys(value).sort();
  for (const key of keys) {
    output[key] = normalizeJson((value as JsonMap)[key]);
  }
  return output;
}

export function canonicalJsonString(value: JsonValue): string {
  return JSON.stringify(normalizeJson(value));
}

export function canonicalJsonBytes(value: JsonValue): Uint8Array {
  return new TextEncoder().encode(canonicalJsonString(value));
}

export function parseJsonMap(raw: string): JsonMap {
  const parsed = JSON.parse(raw) as JsonValue;
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw validationError("unable to parse JSON object");
  }
  return parsed as JsonMap;
}

export function toJsonMap(value: unknown): JsonMap {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw validationError("expected JSON object");
  }
  return value as JsonMap;
}
