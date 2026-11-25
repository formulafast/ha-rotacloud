# RotaCloud Attendance for Home Assistant — development starter

**Not yet installable or production ready.** This first checkpoint implements a server-side API transport and minimal attendance model, with offline unit tests. It has no Home Assistant config flow, coordinator, web endpoint, terminal UI or service registration yet. No real employee identifiers, PINs, API keys, or terminal IDs are included. Do not install on the live HA instance yet.

## Scope

RotaCloud remains the attendance/payroll system of record. An HA custom integration supplies the operational dashboard, while a separate restricted terminal lets staff identify themselves with their existing RotaCloud PIN and clock in/out or start/end breaks. The kiosk must not receive an HA admin token, RotaCloud API key or bulk employee data.

| State | Terminal choices | Confirmation |
| --- | --- | --- |
| Clocked out | Clock in | Actual clock-in and scheduled end, if known |
| Working | Start break / Clock out | Break start or clock-out time |
| On break | End break / Clock out | Current break duration before action; completed break and cumulative shift break duration on return |
| Clocked out after a shift | Clock in | Clock-out, gross shift duration and separate total breaks |

Gross shift duration = actual clock-out minus actual clock-in, without subtracting breaks. Running break and elapsed shift displays are calculated locally. Use UK local time for presentation and Unix timestamps for calculations. Support multiple shifts and breaks; clearly label missing or ambiguous schedules, and do not silently associate a wrong shift.

## Development checkpoints

1. API/model foundation (this checkpoint): tested clock-in/out and break payloads; PIN response minimisation; gross duration; paginated live attendance.
2. HA config flow and coordinator: credential storage in config entries; read-only initial setup; configurable terminal and conservative fallback polling; roster/shifts/attendance reconciliation with correct UK day boundaries and overnight shifts; native staff status entities (due, late, here, break, leaving, gone) and availability; exclude sensitive attributes from entities and recorder. Handle 429 with Retry-After/backoff; do not assume quota.
3. Webhook receiver: validate RotaCloud HMAC against exact raw request body with timestamp tolerance and replay protection, debounce/coalesce refreshes, retain existing office-arrival automation and other webhook destinations. Only one webhook per event; plan migration or fan-out before switching URLs. Do not treat unsigned events as authoritative. Break start/end webhooks were not observed during live testing.
4. Restricted kiosk endpoint and UI: device authentication, server-side rate limit for PIN lookups, short-lived one-use sessions bound to device and employee, no PIN in logs/traces, no raw API responses, TLS, no unrestricted employee-ID action from kiosk. Redact outgoing URL tracing because PIN is part of the RotaCloud endpoint path. Verify account/employee eligibility, role/location, shift choice and terminal permissions. Enforce state transition server-side and serialize per employee. Clear PIN immediately, reset on timeout, block double submission. Never replay an uncertain write automatically; reconcile and show a clear fallback message. Maintain existing RotaCloud terminal for outages. Test concurrent native RotaCloud actions and interrupted requests.
5. Separate operations dashboard: reusable entities, schedule deltas, active and completed break times, total attendance. Any custom card remains optional and visually configurable.
6. CI and controlled pilot: unit/integration/security tests, HA version compatibility, real PIN validation without chat disclosure, scheduled shift association, dedicated terminal registration, confirmation screens, rate-limit behaviour, clock-out with active break of non-zero duration, test-record cleanup with approval. Backup and rollback before live deployment.

## API contract

- GET /pins/{pin} (documented; live PIN validation outstanding)
- GET /users_clocked_in (live-tested)
- POST /users_clocked_in with method=terminal, terminal, user, optional shift (live-tested without shift)
- POST /users_clocked_in/{id} with method=terminal, terminal, action=start_break or end_break (both live-tested; start_break undocumented)
- DELETE /users_clocked_in/{id} with method=terminal, terminal (live-tested, including on active break; saved record closed the break)
- GET /attendance/{id} for completed record reconciliation; immediate clock-out response may omit break details that appear in saved record. Treat these as provisional until reconciled.

No automatic write retries. Request errors intentionally exclude raw URLs or bodies. This is not a complete security boundary: the terminal gateway, access checks, rate limiting, instrumentation review and reconciliation are prerequisites to production.

## Run offline tests

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

References: https://rotacloud-api-docs.netlify.app/ ; https://www.home-assistant.io/docs/ ; https://developers.home-assistant.io/docs/integration_fetching_data/ .
