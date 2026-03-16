import { AcpAgent } from "../src/agent.js";
import { defaultAgentOptions } from "../src/options.js";
import { OverlayClient } from "../src/overlayFramework.js";

function envString(key: string, fallback: string): string {
  const value = process.env[key]?.trim();
  return value ? value : fallback;
}

function envBool(key: string, fallback: boolean): boolean {
  const value = process.env[key]?.trim().toLowerCase();
  if (!value) {
    return fallback;
  }
  if (["1", "true", "yes", "on"].includes(value)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(value)) {
    return false;
  }
  return fallback;
}

async function main(): Promise<void> {
  const fromAgentId = envString("ACP_FROM_AGENT_ID", "agent:overlay.ts.sender@localhost:9032");
  const targetBaseUrl = envString("ACP_TARGET_BASE_URL", "http://localhost:9010");
  const storageDir = envString("ACP_STORAGE_DIR", ".acp-data-overlay-ts-sender");
  const allowInsecureHttp = envBool("ACP_ALLOW_INSECURE_HTTP", true);

  const sender = await AcpAgent.loadOrCreate(fromAgentId, {
    ...defaultAgentOptions(),
    storage_dir: storageDir,
    allow_insecure_http: allowInsecureHttp,
    discovery_scheme: targetBaseUrl.startsWith("http://") ? "http" : "https"
  });
  const client = OverlayClient.create(sender);
  const result = await client.sendAcp(targetBaseUrl, {
    kind: "typescript-overlay-client",
    attributes: {
      source: "acp-sdk-typescript example",
      mode: "overlay"
    }
  });
  // eslint-disable-next-line no-console
  console.log(JSON.stringify(result, null, 2));
}

void main();
