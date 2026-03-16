use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum FailReason {
    UnsupportedVersion,
    UnsupportedCryptoSuite,
    UnsupportedMessageClass,
    InvalidSignature,
    ExpiredMessage,
    PolicyRejected,
    PayloadTooLarge,
    UnsupportedProfile,
}

impl FailReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedVersion => "UNSUPPORTED_VERSION",
            Self::UnsupportedCryptoSuite => "UNSUPPORTED_CRYPTO_SUITE",
            Self::UnsupportedMessageClass => "UNSUPPORTED_MESSAGE_CLASS",
            Self::InvalidSignature => "INVALID_SIGNATURE",
            Self::ExpiredMessage => "EXPIRED_MESSAGE",
            Self::PolicyRejected => "POLICY_REJECTED",
            Self::PayloadTooLarge => "PAYLOAD_TOO_LARGE",
            Self::UnsupportedProfile => "UNSUPPORTED_PROFILE",
        }
    }
}

#[derive(Debug, Error)]
pub enum AcpError {
    #[error("invalid argument: {0}")]
    InvalidArgument(String),
    #[error("validation failed: {0}")]
    Validation(String),
    #[error("transport failure: {0}")]
    Transport(String),
    #[error("crypto failure: {0}")]
    Crypto(String),
    #[error("discovery failure: {0}")]
    Discovery(String),
    #[error("key provider failure: {0}")]
    KeyProvider(String),
    #[error("policy rejected ({reason:?}): {detail}")]
    Processing { reason: FailReason, detail: String },
    #[error("io failure: {0}")]
    Io(#[from] std::io::Error),
    #[error("http failure: {0}")]
    Http(#[from] reqwest::Error),
    #[error("url parse failure: {0}")]
    Url(#[from] url::ParseError),
    #[error("json parse failure: {0}")]
    Json(#[from] serde_json::Error),
}

pub type AcpResult<T> = Result<T, AcpError>;
