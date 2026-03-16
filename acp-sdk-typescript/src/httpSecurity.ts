import { readFileSync, statSync } from "node:fs";
import { Agent as UndiciAgent } from "undici";
import { validationError } from "./errors.js";

export interface HttpSecurityPolicy {
  allow_insecure_http: boolean;
  allow_insecure_tls: boolean;
  mtls_enabled: boolean;
  ca_file?: string | null;
  cert_file?: string | null;
  key_file?: string | null;
}

function normalizeOptionalPath(value: string | null | undefined): string | undefined {
  if (!value || !value.trim()) {
    return undefined;
  }
  const normalized = value.trim();
  const stats = statSync(normalized, { throwIfNoEntry: false });
  if (!stats || !stats.isFile()) {
    throw validationError(`configured file does not exist or is not a file: ${normalized}`);
  }
  return normalized;
}

export function validateHttpUrl(
  rawUrl: string,
  allowInsecureHttp: boolean,
  mtlsEnabled: boolean,
  context: string
): URL {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch (error) {
    throw validationError(`${context} has invalid URL: ${String(error)}`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw validationError(`${context} requires an http(s) URL, got: ${rawUrl}`);
  }
  if (!parsed.hostname.trim()) {
    throw validationError(`${context} URL is missing host: ${rawUrl}`);
  }
  if (parsed.protocol === "http:" && mtlsEnabled) {
    throw validationError(
      `${context} cannot use HTTP (${rawUrl}) when mtls_enabled=true. Use https:// endpoints.`
    );
  }
  if (parsed.protocol === "http:" && !allowInsecureHttp) {
    throw validationError(
      `${context} uses insecure HTTP (${rawUrl}). Set allow_insecure_http=true only for local/dev/demo workflows.`
    );
  }
  return parsed;
}

export function validateHttpClientPolicy(policy: HttpSecurityPolicy, context: string): void {
  const certFile = normalizeOptionalPath(policy.cert_file);
  const keyFile = normalizeOptionalPath(policy.key_file);
  normalizeOptionalPath(policy.ca_file);

  if (policy.mtls_enabled) {
    if (!certFile) {
      throw validationError(`${context} requires cert_file when mtls_enabled=true`);
    }
    if (!keyFile) {
      throw validationError(`${context} requires key_file when mtls_enabled=true`);
    }
  } else if ((certFile && !keyFile) || (!certFile && keyFile)) {
    throw validationError(`${context} requires both cert_file and key_file when either is configured`);
  }
}

export function buildFetchOptions(
  policy: HttpSecurityPolicy
): { dispatcher?: UndiciAgent } {
  validateHttpClientPolicy(policy, "HTTP client configuration");
  if (
    !policy.allow_insecure_tls &&
    !policy.ca_file &&
    !policy.cert_file &&
    !policy.key_file &&
    !policy.mtls_enabled
  ) {
    return {};
  }
  const agent = new UndiciAgent({
    connect: {
      rejectUnauthorized: !policy.allow_insecure_tls,
      ca: policy.ca_file ? readFileSync(policy.ca_file, "utf-8") : undefined,
      cert: policy.cert_file ? readFileSync(policy.cert_file, "utf-8") : undefined,
      key: policy.key_file ? readFileSync(policy.key_file, "utf-8") : undefined
    }
  });
  return { dispatcher: agent };
}

export function warnIfInsecureHttpUsed(endpoint: string, context: string): void {
  if (endpoint.startsWith("http://")) {
    // Keeps visibility similar to Python SDK warnings.
    // eslint-disable-next-line no-console
    console.warn(
      `${context} is using insecure HTTP (${endpoint}) because allow_insecure_http=true`
    );
  }
}
