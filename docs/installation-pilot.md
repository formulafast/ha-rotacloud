# Read-only pilot installation (0.3.1-dev.1)
Do not enable the terminal for real staff yet. The Live card reads only local HA entities, with no direct API requests. Individual staff sensors may be visible to non-admin HA users via the state API even when the dashboard is administrator-only; review access and exclude staff sensors from Recorder before connecting real data. Never give staff a shared HA login. Keep the repository private.

1. Confirm offline CI tests and review changes. Take a HA backup. Schedule a restart outside operating hours.
2. Download this exact revision from GitHub. Copy only custom_components/rotacloud_attendance to the HA configuration directory's custom_components folder (on this instance use existing Samba share or Studio Code Server). Do not overwrite other integrations. Check config; restart.
3. Settings > Devices & services > Add integration > RotaCloud Attendance. Enter API key directly in HA, existing terminal ID, and fallback poll 21600 (6h) or 86400 (24h). No key in chat or repository. Do not set event-only until webhook relay is installed and tested. Setup uses one validation request and four initial data requests (plus pagination).
4. Verify roster/actual attendance, sensor availability, cached refresh timestamp, gross shift duration and break totals against RotaCloud. Existing terminal remains demo.
5. Add webhook relay to existing HA receiver without removing existing office notification logic, after review. No live clock writes or PIN validation until secured gateway is built and tested.
Rollback: remove config entry, remove only this custom component folder, restart at a safe time. Restore previous dashboard from HA edit backup if required.
