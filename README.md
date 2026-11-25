# RotaCloud Attendance for Home Assistant

Unofficial community integration. Version 0.4.0 adds an **opt-in administrator terminal pilot** inside Home Assistant. Attendance viewing remains read-only by default. RotaCloud remains the system of record.

## Features
- Staff attendance status and aggregate counts.
- Scheduled and actual shift times, break information, and gross shift duration.
- Conservative configurable polling, cached roster data, and API rate-limit backoff.
- Optional refresh via a trusted internal HA event. Webhook configuration is separate.
- Optional PIN-based clocking through authenticated, administrator-only WebSocket commands. No clocking services or HTTP terminal endpoints are registered.
- Packaged `ff-staff-terminal` card for live clocking; the separate `ff-staff-preview` remains a fictional demonstration.

## Installation
Requires Home Assistant 2026.11 or newer. Tested using HA 2026.11.3 with simulated API responses.
1. Back up HA and plan for a restart outside operational hours if needed.
2. Settings > Marketplace > Add from link: https://github.com/formulafast/ha-rotacloud . Connect GitHub if prompted, select Integration if requested, and install the versioned release.
3. Before configuring real credentials, review HA user access and Recorder exclusions. Individual staff entities are not restricted to administrators simply by hiding the dashboard.
4. Add RotaCloud Attendance from Settings > Devices & services. Enter credentials directly in HA, not in GitHub or chat. Choose conservative polling (up to 86400 seconds).
5. Compare actual attendance with RotaCloud before relying on the dashboard.

See [pilot installation](docs/installation-pilot.md) and [0.4.0 terminal setup, limitations and rollback](docs/release-notes-0.4.0.md). The terminal JavaScript is packaged with the integration; its dashboard resource must be registered separately. Existing dashboard resources are not automatically changed.

## Privacy and security
Employee names and attendance are sensitive operational data. Only use the individual sensors in a trusted HA instance with authorised users. The integration excludes selected attributes from Recorder but not the state history itself; configure explicit Recorder exclusions before connecting real data. The live terminal requires an existing trusted administrator session and is not a restricted staff account. Dashboard visibility is not an access control boundary. Keep API keys and PINs private. Clocking stays disabled until explicitly enabled. No production security certification is claimed.

## Tests
Offline: `python -m pip install -r requirements-dev.txt` then `python -m unittest discover -s tests -v`.
Isolated HA: Python 3.14, `python -m pip install pytest-homeassistant==2026.11.3` then `python -m pytest -v ha_tests`.
Browser: `npm ci`, `npx playwright install chromium`, then `npm test` (optional `CHROMIUM_PATH` for an existing browser). All responses are fictional. See GitHub Actions for results. Live API compatibility, upstream terminal permissions and operational acceptance remain to be verified.

References: https://www.home-assistant.io/docs/ ; https://www.home-assistant.io/integrations/marketplace/ ; https://rotacloud-api-docs.netlify.app/
