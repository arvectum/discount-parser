# DP-SEC-001 — local control and redaction

The local web panel rejects mutating requests carrying a non-loopback `Origin` or fallback `Referer`; TrustedHostMiddleware rejects untrusted hosts. Loopback URLs remain usable.

Logging redaction covers application credentials, generic token/password/secret forms, Authorization/Proxy-Authorization, cookies/API keys, Telegram channel/admin identifiers and credentials embedded in HTTP(S) URLs. Structured logging extras are recursively redacted before JSON serialization.
