/*
 * Copyright 2026 ACP Project
 * Licensed under the Apache License, Version 2.0
 * See LICENSE file for details.
 */

export type FailReason =
  | "UNSUPPORTED_VERSION"
  | "UNSUPPORTED_CRYPTO_SUITE"
  | "UNSUPPORTED_PROFILE"
  | "INVALID_SIGNATURE"
  | "EXPIRED_MESSAGE"
  | "POLICY_REJECTED";

export class AcpError extends Error {
  public readonly code:
    | "INVALID_ARGUMENT"
    | "VALIDATION"
    | "DISCOVERY"
    | "TRANSPORT"
    | "CRYPTO"
    | "PROCESSING"
    | "KEY_PROVIDER";

  public readonly reason?: FailReason;

  public constructor(
    code:
      | "INVALID_ARGUMENT"
      | "VALIDATION"
      | "DISCOVERY"
      | "TRANSPORT"
      | "CRYPTO"
      | "PROCESSING"
      | "KEY_PROVIDER",
    message: string,
    reason?: FailReason
  ) {
    super(message);
    this.name = "AcpError";
    this.code = code;
    this.reason = reason;
  }
}

export function invalidArgument(message: string): AcpError {
  return new AcpError("INVALID_ARGUMENT", message);
}

export function validationError(message: string): AcpError {
  return new AcpError("VALIDATION", message);
}

export function discoveryError(message: string): AcpError {
  return new AcpError("DISCOVERY", message);
}

export function transportError(message: string): AcpError {
  return new AcpError("TRANSPORT", message);
}

export function cryptoError(message: string): AcpError {
  return new AcpError("CRYPTO", message);
}

export function processingError(reason: FailReason, detail: string): AcpError {
  return new AcpError("PROCESSING", detail, reason);
}

export function keyProviderError(message: string): AcpError {
  return new AcpError("KEY_PROVIDER", message);
}
