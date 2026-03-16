import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { AddressInfo } from "node:net";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { AcpAgent } from "../src/agent.js";
import { verifyIdentityDocument } from "../src/identity.js";
import { defaultAgentOptions } from "../src/options.js";
import { OverlayClient, OverlayFrameworkRuntime } from "../src/overlayFramework.js";
import { JsonMap, JsonValue } from "../src/jsonSupport.js";

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

function writeJson(res: ServerResponse, payload: JsonValue, status = 200): void {
  const body = JSON.stringify(payload);
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.end(body);
}

describe("Overlay framework runtime", () => {
  it("exposes well-known headers and rejects invalid body", async () => {
    const root = mkdtempSync(join(tmpdir(), "acp-ts-overlay-runtime-"));
    try {
      const receiver = await AcpAgent.loadOrCreate("agent:receiver.framework@localhost:9551", {
        ...defaultAgentOptions(),
        storage_dir: join(root, "receiver"),
        endpoint: "http://localhost:9551/acp/inbox",
        allow_insecure_http: true,
        discovery_scheme: "http"
      });
      const runtime = OverlayFrameworkRuntime.create(
        receiver,
        "http://localhost:9551",
        (payload) => ({ accepted: true, echo: payload })
      );
      const headers = OverlayFrameworkRuntime.wellKnownHeaders();
      expect(headers["Cache-Control"]).toBe("public, max-age=300");
      const wellKnown = runtime.wellKnownDocument();
      expect(wellKnown.agent_id).toBe("agent:receiver.framework@localhost:9551");

      const invalidResponse = await runtime.handleMessageBody(["invalid"]);
      expect(invalidResponse.status_code).toBe(400);
      expect(invalidResponse.body.state).toBe("FAILED");
      expect(invalidResponse.body.reason_code).toBe("POLICY_REJECTED");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("overlay client bootstraps from well-known and sends payload", async () => {
    const root = mkdtempSync(join(tmpdir(), "acp-ts-overlay-client-"));
    const receiver = await AcpAgent.loadOrCreate("agent:receiver.framework@localhost:9552", {
      ...defaultAgentOptions(),
      storage_dir: join(root, "receiver"),
      endpoint: "http://localhost:9552/acp/inbox",
      allow_insecure_http: true,
      discovery_scheme: "http"
    });
    expect(verifyIdentityDocument(receiver.identity_document)).toBe(true);
    const server = createServer(async (req, res) => {
      if (req.method === "GET" && req.url === "/.well-known/acp") {
        const port = (server.address() as AddressInfo).port;
        const baseUrl = `http://127.0.0.1:${port}`;
        writeJson(res, {
          agent_id: receiver.agentId(),
          identity_document: `${baseUrl}/api/v1/acp/identity`,
          transports: {
            http: {
              endpoint: `${baseUrl}/acp/inbox`
            }
          },
          version: "1.0",
          security_profile: "http"
        });
        return;
      }
      if (req.method === "GET" && req.url === "/api/v1/acp/identity") {
        writeJson(res, { identity_document: receiver.identity_document });
        return;
      }
      if (req.method === "POST" && req.url === "/acp/inbox") {
        await readBody(req);
        writeJson(res, { status: "accepted" });
        return;
      }
      writeJson(res, { error: "not found" }, 404);
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));

    try {
      const port = (server.address() as AddressInfo).port;
      const baseUrl = `http://127.0.0.1:${port}`;
      const sender = await AcpAgent.loadOrCreate("agent:sender.framework@localhost:9553", {
        ...defaultAgentOptions(),
        storage_dir: join(root, "sender"),
        allow_insecure_http: true,
        discovery_scheme: "http"
      });
      const client = OverlayClient.create(sender);
      const response = await client.sendAcp(baseUrl, { kind: "runtime-outbound" } as JsonMap);
      const target = response.target as JsonMap;
      expect(target.agent_id).toBe("agent:receiver.framework@localhost:9552");
      expect(target.well_known_url).toBe(`${baseUrl}/.well-known/acp`);
      const sendResult = response.send_result as JsonMap;
      const outcomes = sendResult.outcomes as JsonValue[];
      expect(Array.isArray(outcomes)).toBe(true);
      expect(outcomes.length).toBe(1);
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      rmSync(root, { recursive: true, force: true });
    }
  });
});
