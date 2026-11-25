# Publication gate

This repository is still a development project. The HA integration is read-only; the terminal backend is not exposed. No production deployment or security certification.

Targeted source scan of 26 current files and 13 distinct earlier file versions across six reachable commits found no matching known real staff or attendance identifiers, internal IP addresses, private remote HA URLs or common embedded credential patterns. This is a pattern-based check, not exhaustive secret detection. The repository owner and author attribution remain visible if published. Historical demonstration branding is retained in Git history; current generic demonstration is fictional. No real PINs should ever be entered in the demo.

Before publication/install:
- Run all offline tests, HA integration setup/unload/reauthentication tests and dependency checks.
- Audit all refs, tags, issues, PRs, artifacts and secret-scanner results; verify no credentials, staff details or network data.
- Ensure individual employee information is only available to authorised management users, including entity API, recorder, backups and dashboard exposure. Dashboard admin visibility alone is insufficient. Keep kiosk unauthenticated to the general HA API.
- Validate upstream response shapes, rate limits, shift association, pagination, expiry/recovery and webhook security. No live clocking endpoints until independent gateway/security review.
- Prepare a versioned read-only pilot on the default branch; never release the development branch blindly.
- The owner must review GitHub visibility change themselves. Marketplace custom links require a public repository with hacs.json and valid integration structure.
- Keep actual deployment and branded dashboard resources private.

References: https://www.home-assistant.io/integrations/marketplace/ and https://contributors.home-assistant.io/marketplace/guides/integrations/
