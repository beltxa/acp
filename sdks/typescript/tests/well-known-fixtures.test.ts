import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { JsonValue } from "../src/jsonSupport.js";
import { parseWellKnownDocument } from "../src/wellKnown.js";

const VECTORS_DIR = join(process.cwd(), "..", "tests", "vectors", "well_known");

function readRaw(name: string): string {
  return readFileSync(join(VECTORS_DIR, name), "utf-8");
}

function loadValue(name: string): JsonValue {
  return JSON.parse(readRaw(name)) as JsonValue;
}

describe("Well-known fixtures", () => {
  it("valid fixture parses", () => {
    const parsed = parseWellKnownDocument(loadValue("valid_basic.json"));
    expect(parsed.agent_id).toBe("agent:shipping.bot@company.local");
    expect(parsed.version).toBe("1.0");
  });

  it.each([
    "invalid_missing_agent_id.json",
    "invalid_missing_version.json",
    "invalid_identity_document_type.json",
    "invalid_identity_document_relative_path.json",
    "invalid_identity_document_url.json",
    "invalid_transports_type.json",
    "invalid_transport_hint_shape.json",
    "invalid_transport_endpoint_type.json",
    "invalid_transport_endpoint_url.json",
    "invalid_version.json",
    "invalid_security_profile.json"
  ])("invalid fixture fails validation: %s", (fixture) => {
    expect(() => parseWellKnownDocument(loadValue(fixture))).toThrow();
  });

  it("malformed json fixture fails parse", () => {
    expect(() => JSON.parse(readRaw("malformed_json.txt"))).toThrow();
  });
});
