# RotaCloud Attendance for Home Assistant

Unofficial community integration. Version 0.3.1 is a **read-only pilot**, not a production payroll or staff clocking system. RotaCloud remains the system of record.

## Features
- Staff attendance status and aggregate counts.
- Scheduled and actual shift times, break information, and gross shift duration.
- Conservative configurable polling, cached roster data, and API rate-limit backoff.
- Optional refresh via a trusted internal HA event. Webhook configuration is separate.
- No live clocking services or HTTP terminal endpoints are registered. The terminal demonstration uses fictional data.

## Installation
Requires Home Assistant 2026.11 or newer. Tested using HA 2026.11.3 with simulated API responses.
1. Back up HA and plan for a restart outside operational hours if needed.
2. Settings > Marketplace > Add from link: https://github.com/formulafast/ha-rotacloud . Connect GitHub if prompted, select Integration if requested, and install the versioned release.
3. Before configuring real credentials, review HA user access and Recorder exclusions. Individual staff entities are not restricted to administrators simply by hiding the dashboard.
4. Add RotaCloud Attendance from Settings > Devices & services. Enter credentials directly in HA, not in GitHub or chat. Choose conservative polling (up to 86400 seconds).
5. Compare actual attendance with RotaCloud before relying on the dashboard.

See [pilot installation](docs/installation-pilot.md). The optional dashboard JavaScript is not automatically installed by the integration.

## Privacy and security
Employee names and attendance are sensitive operational data. Only use the individual sensors in a trusted HA instance with authorised users. The integration excludes selected attributes from Recorder but not the state history itself; configure explicit Recorder exclusions before connecting real data. Do not give kiosk users access to general HA credentials. Keep API keys and PINs private. No live write functionality is exposed through HA. No production security certification is claimed.

## Tests
Offline: `python -m pip install -r requirements-dev.txt` then `python -m unittest discover -s tests -v`.
Isolated HA: Python 3.14, `python -m pip install pytest-homeassistant==2026.11.3` then `python -m pytest -v ha_tests`.
See GitHub Actions for results. Live API compatibility, access control and operational acceptance remain to be verified.

References: https://www.home-assistant.io/docs/ ; https://www.home-assistant.io/integrations/marketplace/ ; https://rotacloud-api-docs.netlify.app/
