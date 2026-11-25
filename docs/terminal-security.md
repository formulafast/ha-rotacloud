# Restricted terminal development

The kiosk must not hold HA login credentials or the RotaCloud API key. The gateway is an offline-testable HTTP boundary and is deliberately NOT registered in HA yet. No real clocking is enabled by this commit.

Architecture: administrator provisions a random 256-bit device key, server stores only its SHA-256 digest; kiosk pairs over HTTPS and receives a scoped HttpOnly Secure SameSite=Strict cookie. Explicit trusted origin and restricted network required. Device revocation removes the digest. Staff identify with their own PIN; server issues a single-use 20-second device-bound session; each action is checked against freshly read attendance. No arbitrary staff IDs from browser. No automatic retries after uncertain writes.

Next implementation gates:
- HA view adapter with authenticated admin-only provisioning/revocation, durable digest storage, disabled-by-default pilot allowlist, explicit unscheduled-clock-in policy and fresh roster eligibility. Handle unload/reload and in-flight writes safely.
- Verify actual HA TLS, proxy and client IP semantics; use dedicated kiosk origin with no other untrusted scripts, and firewall restrictions. Do not expose terminal endpoints to the public internet or trust browser-supplied forwarded headers. Prevent caching, request logging and PIN tracing.
- Standalone kiosk UI with no HA credentials, no personal data storage, short session, explicit confirmation and uncertain-outcome fallback. Pairing requires local administrator action. Use separate browser profile.
- Reconcile confirmed writes and unknown outcomes with coordinator, avoid duplicate webhook reads, and test live clocking only with explicit pilot employee approval.
- Validate real PIN shape and shift association; verify data access, HA permissions, rate limits and actual API response schemas before enabling any live clocking.

References: https://www.home-assistant.io/docs/configuration/securing/ ; https://www.home-assistant.io/docs/configuration/remote ; https://rotacloud-api-docs.netlify.app/
