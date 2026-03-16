package acp

import "fmt"

type FailReason string

const (
	FailUnsupportedVersion     FailReason = "UNSUPPORTED_VERSION"
	FailUnsupportedCryptoSuite FailReason = "UNSUPPORTED_CRYPTO_SUITE"
	FailUnsupportedProfile     FailReason = "UNSUPPORTED_PROFILE"
	FailInvalidSignature       FailReason = "INVALID_SIGNATURE"
	FailExpiredMessage         FailReason = "EXPIRED_MESSAGE"
	FailPolicyRejected         FailReason = "POLICY_REJECTED"
)

type ErrorCode string

const (
	ErrInvalidArgument ErrorCode = "INVALID_ARGUMENT"
	ErrValidation      ErrorCode = "VALIDATION"
	ErrDiscovery       ErrorCode = "DISCOVERY"
	ErrTransport       ErrorCode = "TRANSPORT"
	ErrCrypto          ErrorCode = "CRYPTO"
	ErrProcessing      ErrorCode = "PROCESSING"
	ErrKeyProvider     ErrorCode = "KEY_PROVIDER"
)

type AcpError struct {
	Code   ErrorCode
	Reason *FailReason
	Detail string
}

func (e *AcpError) Error() string {
	if e == nil {
		return ""
	}
	if e.Reason != nil {
		return fmt.Sprintf("%s (%s): %s", e.Code, *e.Reason, e.Detail)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Detail)
}

func newError(code ErrorCode, detail string) error {
	return &AcpError{
		Code:   code,
		Detail: detail,
	}
}

func newProcessingError(reason FailReason, detail string) error {
	return &AcpError{
		Code:   ErrProcessing,
		Reason: &reason,
		Detail: detail,
	}
}

func InvalidArgument(detail string) error { return newError(ErrInvalidArgument, detail) }
func ValidationError(detail string) error { return newError(ErrValidation, detail) }
func DiscoveryError(detail string) error  { return newError(ErrDiscovery, detail) }
func TransportError(detail string) error  { return newError(ErrTransport, detail) }
func CryptoError(detail string) error     { return newError(ErrCrypto, detail) }
func KeyProviderError(detail string) error {
	return newError(ErrKeyProvider, detail)
}

func ProcessingError(reason FailReason, detail string) error {
	return newProcessingError(reason, detail)
}
