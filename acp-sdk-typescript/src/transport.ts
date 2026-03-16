import { AcpMessage, messageToMap } from "./messages.js";
import { HttpSecurityPolicy, buildFetchOptions, validateHttpUrl } from "./httpSecurity.js";
import { JsonMap, parseJsonMap } from "./jsonSupport.js";
import { transportError } from "./errors.js";

export interface TransportResponse {
  status_code: number;
  body?: JsonMap;
  raw_body: string;
}

export class TransportClient {
  private readonly fetchOptions: ReturnType<typeof buildFetchOptions>;

  public constructor(
    private readonly timeoutSeconds: number,
    private readonly policy: HttpSecurityPolicy
  ) {
    this.fetchOptions = buildFetchOptions(policy);
  }

  public async postJson(url: string, body: JsonMap): Promise<TransportResponse> {
    validateHttpUrl(url, this.policy.allow_insecure_http, this.policy.mtls_enabled, "HTTP transport request");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Math.max(1, this.timeoutSeconds) * 1000);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
        ...this.fetchOptions
      } as RequestInit);
      const rawBody = await response.text();
      let parsedBody: JsonMap | undefined;
      try {
        parsedBody = parseJsonMap(rawBody);
      } catch {
        parsedBody = undefined;
      }
      return {
        status_code: response.status,
        raw_body: rawBody,
        body: parsedBody
      };
    } catch (error) {
      throw transportError(`HTTP request failed: ${String(error)}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  public async sendToRelay(relayUrl: string, message: AcpMessage): Promise<JsonMap> {
    const relayEndpoint = relayUrl.endsWith("/") ? `${relayUrl}messages` : `${relayUrl}/messages`;
    const response = await this.postJson(relayEndpoint, messageToMap(message));
    if (response.status_code !== 200) {
      throw transportError(
        `Relay returned HTTP ${response.status_code} for message ${message.envelope.message_id}`
      );
    }
    if (!response.body) {
      throw transportError("Relay returned non-JSON response");
    }
    return response.body;
  }
}
