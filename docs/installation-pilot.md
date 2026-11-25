# Read-only pilot installation (0.3.1)

Do not configure the live terminal. The Live card reads local HA entities and is optional. Individual staff sensors may be visible through the state API to non-admin HA users even with an admin-only dashboard. Before entering real credentials, restrict HA access to authorised users and configure Recorder exclusions for individual staff sensors (for example exclude entity glob sensor.rotacloud_* if acceptable, including counts). Backups and entity registry also contain identifying data. Never share HA login with the kiosk.

1. Check GitHub Actions for successful tests on the release revision. Back up HA and choose a safe restart window.
2. Settings > Marketplace > Add from link > https://github.com/formulafast/ha-rotacloud. Select Integration if prompted. Install 0.3.1. Follow HA prompts for restart if required. Manual fallback: copy only custom_components/rotacloud_attendance into the HA custom_components directory.
3. Only after access and Recorder review, Settings > Devices & services > Add integration > RotaCloud Attendance. Enter the API key and terminal ID directly in HA. Choose fallback poll 86400 seconds (24h) for the lowest scheduled polling frequency. Initial setup needs one validation request and four initial reads plus pagination. Roster/history refreshes and event-driven reads may add requests. Do not use event-only until the relay is tested.
4. Compare employee status, schedules and attendance with RotaCloud. Verify stale/unavailable states. Dashboard frontend resources are separate.
5. Review existing webhook automation before adding a refresh relay. Keep existing arrival notification logic and destinations.
6. Live terminal remains disabled until a separate secured gateway is implemented and validated.

Rollback: remove the config entry, uninstall the integration, and restart at a safe time if required. Review retained recorder and registry data.
