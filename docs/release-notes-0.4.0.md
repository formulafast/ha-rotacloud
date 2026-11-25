# 0.4.0 — live terminal inside Home Assistant

The Staff Terminal can now identify employees using their RotaCloud PIN and perform clock-in, clock-out, start-break and end-break actions over HA's authenticated WebSocket connection. No standalone kiosk or unauthenticated clocking page is installed.

Clocking is off by default, including on upgrades. Enable **Enable live HA terminal clocking (administrators only)** in the integration's options. Only HA administrators may use the terminal; hiding navigation or a dashboard does not grant or restrict backend access. This pilot uses an existing trusted administrator session, not a restricted staff login. The terminal ID already stored in the integration is used for upstream writes. Account-wide, non-deleted employees are eligible; this version does not add per-location staff filtering.

## Dashboard installation

1. Install this version and restart HA so the new Python transport loads.
2. Register `/rotacloud_attendance/static/staff-terminal.js?v=0.4.0` as a JavaScript module in dashboard resources. The JavaScript is included in the integration package; it contains no credentials.
3. Replace only the demo card in **Staff → Terminal** with:

```yaml
type: custom:ff-staff-terminal
entry_id: YOUR_ROTACLOUD_CONFIG_ENTRY_ID
pin_length: 4
```

Use the integration's config entry ID, not an entity ID or terminal ID. PIN length is configurable from 1–12; keep it at the length actually used by your staff. Keep **Staff → Live** unchanged. Enable clocking in integration options when ready for the supervised pilot. The old `ff-staff-preview` card remains a clearly labelled offline demonstration.

## Behaviour and limits

- The server validates eligibility from the cached active employee directory, offers today's remaining published shifts, and requires a shift selection when more than one is available. With no remaining shift, the card explicitly offers an unscheduled clock-in; the upstream terminal/account settings can still reject it.
- Sessions expire after 20 seconds, belong to one authenticated connection and permit one action. A new PIN replaces that connection's previous session. Disconnect/unload cleans sessions. There is a shared ceiling of eight PIN lookups per minute.
- A fresh attendance read precedes every write. Polls and complete terminal transactions share one lock. A confirmed response updates the Live sensors immediately, then queues reconciliation. There are no automatic write retries; an uncertain result says to check RotaCloud first.
- The UI hides employee details after cancellation, timeout or five seconds on the confirmation screen. Gross shift duration does not subtract breaks. Clock-out break totals remain provisional until RotaCloud reconciliation.
- PINs and session tokens are memory-only, are never HA state/service/event data, and use HA's redacted protocol fields. RotaCloud's upstream PIN endpoint includes the PIN in its URL path: keep HTTP tracing/proxy logging disabled or redacted.
- No production attendance is written by the automated tests. Live API compatibility and actual terminal permissions still need a supervised clock-in/break/clock-out pilot; unit tests cannot prove these.

## Validation

Offline API/model/terminal tests; isolated HA 2026.11.3 lifecycle and real WebSocket tests; browser interaction tests with fictional responses. The WebSocket tests cover administrator gating, disabled clocking, connection-bound one-use sessions, invalid input and redaction, unload, full clocking flow, uncertain writes and concurrent polling.

## Rollback

Disable live clocking in the options, restore the Terminal card to `custom:ff-staff-preview`, and continue using the existing RotaCloud terminal. Removing the new resource is optional. Downgrading Python files requires another HA restart; attendance already written in RotaCloud is not undone by a downgrade.

References: https://www.home-assistant.io/docs/ ; https://contributors.home-assistant.io/core/internals/websocket-api/ ; https://rotacloud-api-docs.netlify.app/
