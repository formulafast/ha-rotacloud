# v0.5.0 — Dashboard, planning and break warnings

## Dashboard

- Rename Live Attendance to **Dashboard** and remove its title logo. The supplied logo is now packaged in the integration's local `brand/` directory for HA 2026.3+.
- Manual Refresh button with icon, administrator permission check, shared in-flight request and 30-second server cooldown. It refreshes attendance, history, staff, shifts, leave and availability. It works with terminal clocking disabled.
- Move the last API refresh timestamp to the bottom right of the main table, showing date/time only.
- Neutral counters until selected; status icons retain their colours. Here uses a tick and Due an hourglass. Filter controls remain stable across HA updates.
- Centre Clock-In/Clock-Out along with the other attendance columns; make timing pills match the subtle status-pill design. Keep completed-shift flags at the right edge of the duration cell.
- Breaks Today shows the daily total only, including the current break. An amber warning icon appears when configured break conditions are unmet.
- On Leave and Available filters/counts plus a planning table. Availability means explicitly recorded available spans; empty/unavailable records do not imply availability. Only approved leave is shown. Exact times appear where supplied; full days show All Day. The RotaCloud leave endpoint commonly supplies AM/PM or day fractions rather than exact times: these are labelled honestly, without invented start/end times.
- Still-open clockings from before today's HA-local date move into a conditional **Still Clocked In From Yesterday** table below the attendance/planning tables. They no longer contribute to today's attendance counters.

## Terminal

- Remove the RotaCloud attendance footer; add clocking and break icons.
- Current Break, Total Break Time and End Break now sit together, followed by a divider and the clocked-in/scheduled-finish/clock-out section.
- Physical keyboard/keypad number entry is supported after clicking/tapping the terminal. Backspace deletes and Escape cancels. Input remains scoped to the terminal, not a global dashboard listener.
- Existing PIN, administrator access, duplicate-write and uncertain-result safeguards remain in place.

## Break configuration

The integration Configure form now uses number boxes for thresholds and explains each field. For **Age under 18** and **Age 18+**, configure:

- Minimum Break Time in minutes. Zero disables warnings for that age band (the upgrade default).
- Qualifying Shift Length in hours/minutes: actual work so far in the current clocking, excluding recorded breaks. It does not use the scheduled shift duration.
- Show warning if minimums not met after, in hours/minutes: elapsed time since the current clock-in, including breaks.

Both timing conditions must be reached and the current clocking's recorded break total must remain below the minimum. Warnings clear once that minimum is met. The dashboard still displays the total breaks for the whole day, including earlier clockings. Unknown dates of birth do not silently become adult warnings. Age bands are derived from the existing staff read, re-evaluated at date rollover; dates of birth are not exposed in entity states or attributes. No payroll times are changed.

## API and HA load

- No additional periodic polling loop. The configured attendance poll interval remains unchanged (minimum 30 minutes when enabled), and event-only mode remains supported.
- Leave/availability are cached for six hours and fetched only during an existing refresh when expired, at day rollover, following their refresh event, or through the manual Refresh button. Missing planning permissions leave attendance usable.
- A normal cached refresh needs one active-attendance read. Existing history reconciliation and roster expiry may add reads. A startup/day-change/manual full batch is six endpoint reads before pagination: users, shifts, active attendance, history, leave and availability. There are no per-person age requests.
- Repeated manual clicks across clients share one in-flight batch, then observe the 30-second cooldown.
- The existing one-minute local HA projection is retained. Both cards update their display at most once per minute from cached state, skip hidden pages and never poll the API from a display timer. Unrelated HA state changes do not redraw the Dashboard.
- Only two fixed planning count entities are added. Detailed rows and timer attributes are excluded from Recorder history.

## Upgrade

1. Merge this PR, publish the `v0.5.0` release, then install v0.5.0 through HACS and restart HA.
2. In dashboard Resources, **replace** the existing module URLs with:
   - `/rotacloud_attendance/static/staff-live.js?v=0.5.0`
   - `/rotacloud_attendance/static/staff-terminal.js?v=0.5.0`
3. Keep only one resource per card, then hard-refresh the browser. Existing `custom:ff-staff-live` and `custom:ff-staff-terminal` card configurations and dashboard tabs can stay in place.
4. Open RotaCloud Attendance > Configure, set the break-warning fields for each age band, and save. Existing clocking/terminal options and timing colours are retained. Warnings stay off until Minimum Break Time is greater than zero.
5. Press Refresh on the Dashboard and compare today's attendance, leave and availability with RotaCloud. Planning requires read permission for `/leave` and `/availability`.

## Validation and rollback

56 offline tests, 26 isolated HA 2026.11.3 tests and 12 Chromium interaction tests cover the API projections, configuration, permission checks, manual refresh coalescing, cache reuse, no-network timer ticks, day rollover separation, keyboard input and dashboard layouts. Desktop/mobile browser layouts are checked with fictional attendance. No real attendance mutations are used for automated tests.

To roll back, restore v0.4.1, restart HA and restore both resource URLs to `?v=0.4.1`. RotaCloud attendance is unchanged by a downgrade. Disable live HA terminal clocking to stop HA writes independently of the Dashboard.

References: https://www.home-assistant.io/docs/ ; https://contributors.home-assistant.io/core/integrations/brands/ ; https://rotacloud-api-docs.netlify.app/
