# v0.4.1 — terminal fixes and Live Attendance improvements

## Terminal

- Check the configured RotaCloud terminal before each action. An inactive terminal produces a clear error rather than the previous generic failure.
- New **Activate configured terminal for HA** option explicitly permits launching that terminal when inactive. This option is off by default. It opens only the configured terminal; it never selects another terminal, changes photo requirements, or retries an uncertain activation/write. Activation happens on an action, not at startup or PIN entry. Only enable it for a terminal intended for HA use; it opens that same terminal in RotaCloud.
- Terminal ID is now editable in the integration options without re-entering the API key. The original configured ID remains the default.
- **Breaks today** includes recorded breaks from earlier clock-ins today, plus the current clock-in. Previously the terminal only displayed the current attendance record's breaks.
- Rejections distinguish inactive/invalid terminals, photo requirements, API permissions, rate limits and HTTP errors without exposing raw responses, URLs, PINs or credentials.

## Live Attendance

- Status pills; early/late pills beside actual clock-in/out times.
- Four independent timing thresholds and colour pickers in the integration options: early clock-in, late clock-in, early clock-out and late clock-out. Defaults are yellow for early and red for late. Pills appear only beyond the configured threshold; these display settings do not change payroll times or the existing late-status grace period.
- Supplied logo, individual status/filter icons, centred Status/Scheduled/Breaks today/Shift duration columns, and a right-aligned chequered flag for staff whose status is Gone and have a recorded clock-out.
- Stable filter buttons survive HA data updates and timer ticks. Previously a render between pointer-down and pointer-up could discard the click.
- Live card and logo are now packaged with the integration, alongside the Terminal card.

## Upgrade

1. Install v0.4.1 through HACS and restart HA.
2. Under dashboard Resources, **replace** the old Live Attendance JavaScript resource URL with `/rotacloud_attendance/static/staff-live.js?v=0.4.1`, type JavaScript module. Replace the Terminal module URL with `/rotacloud_attendance/static/staff-terminal.js?v=0.4.1`. Keep only one resource for each card: an older resource loaded first would retain the older custom element.
3. Hard-refresh the browser after updating both URLs. The existing `custom:ff-staff-live` and `custom:ff-staff-terminal` card configurations and tab locations can stay as they are. The logo is served automatically; `logo_url` on the Live card optionally overrides it.
4. In the RotaCloud Attendance integration's Configure modal, check the terminal ID and enable **Activate configured terminal for HA** if HA should open that terminal when inactive. Leave **Enable live HA terminal clocking** enabled. Save. Timing thresholds and colours are available in this same form.
5. Pilot clocking with your own PIN and compare the result with RotaCloud. Automated tests use fictional responses and do not confirm production API compatibility or change real attendance.

If RotaCloud continues to reject an action, the new error reports the safe HTTP status or preflight reason. Do not repeatedly resubmit an uncertain attendance write; check RotaCloud first. An activation failure does not send the attendance mutation. The extra terminal preflight adds one read per action, and activating an inactive terminal adds one POST; existing cooldown and no-retry protections remain in effect.

## Validation and rollback

Offline API/model/terminal tests, isolated HA 2026.11.3 WebSocket/configuration tests, and browser interaction tests cover daily break totals, opt-in activation, unchanged photo requirements, duplicate/uncertain writes, configurable pills and a data update between pointer-down and pointer-up. Desktop/mobile layouts are visually checked with fictional attendance.

To stop HA clocking, disable **Enable live HA terminal clocking** and use the existing RotaCloud terminal. Disabling the activation option stops future HA activation attempts; it does not close an already-open terminal. Restoring v0.4.0 requires a restart and restoring the old Live resource URL. Existing RotaCloud attendance is not undone by a downgrade.

References: https://www.home-assistant.io/docs/ ; https://rotacloud-api-docs.netlify.app/
