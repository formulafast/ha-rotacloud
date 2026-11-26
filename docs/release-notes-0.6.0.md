# v0.6.0 — visually configurable cards

## Cards and visual editors

After updating the two existing JavaScript resources, Add card offers:

| Card | Purpose and visual options |
| --- | --- |
| RotaCloud Status | One status counter: Clocked in, Here, On break, Leaving, Due, Late, Gone, On Leave or Available. Choose integration, title, icon, colour, filter group, and click behaviour (filter, no action, entity details, navigate). |
| RotaCloud Table | Choose Live attendance, Leave, Availability, or Still Clocked In From Yesterday. Choose integration, title, visible columns, sorting, default filter, linked filter behaviour, hide when empty, Refresh button and refresh timestamp. |
| RotaCloud Terminal | Choose integration, heading, subtitle and comfortable/compact layout. No PIN-length field is exposed in the visual editor. Existing PIN behaviour is preserved. |
| RotaCloud Dashboard | The existing combined Dashboard, with an optional title, integration selection and optional filter group. Existing configurations remain valid. |

Status and Table cards use the default filter group `attendance`. A Status click filters tables in the same group, integration and dashboard view. Clicking the same status again clears that filter. Use different group names for independent sets; leave the group blank to disconnect a card. A table can also turn off Respond to linked Status cards and use its own default filter. Card editor previews are isolated from live filter groups. Filtering is local to that browser; no helpers, backend writes or API requests are needed.

The existing status/timing pills, icons, configured thresholds, break warnings, completion flags, daily break totals, planning labels and previous-day separation are shared with the new tables. The terminal retains its PIN/session, permission and duplicate-write protections. The integration auto-selects when there is only one; otherwise choose it in the editor. Integration-scoped entity metadata prevents staff from different entries being combined.

Every attendance table footer now starts **Last API refresh:** before its local date/time, for example **Last API refresh: 26 Nov, 01:13**. Standalone planning and previous-day tables can show it too.

## Sections layouts

All four card types implement HA's Sections grid sizing API as well as Masonry sizing. Status cards default to three of the section's twelve columns and two grid rows; tables, Terminal and Dashboard default to twelve columns. Use the card's Layout tab/HA resizing controls to change width. Tables and Terminal use automatic height so their changing content remains visible. Tables scroll horizontally at narrow widths; the Status button fills its grid cell.

Suggested arrangement: place Status cards across the top of a Sections view, followed by a full-width Live attendance table, separate Leave and Availability tables, and a Yesterday table with Hide when empty enabled (the default for that table). Put Terminal in whichever section or tab suits the kiosk. Keep matching filter groups within the same view. A wider section is useful for attendance tables.

## Lightweight operation

There is no additional API polling, backend interval, entity or helper. All cards consume the existing integration cache. One shared one-minute browser timer serves mounted tables, Dashboard and Terminal; Status counters need no timer. It stops when the last timed card is removed and skips hidden documents. Shared state projections/signatures avoid rebuilding the same data for each card, and unrelated HA state updates do not redraw the cards. Concurrent Refresh clicks share one browser request in addition to the existing server coalescing and 30-second cooldown. No real attendance writes occur on card creation, preview, layout changes or filtering.

## Upgrade and add cards

1. Merge the PR and publish **v0.6.0** as a pre-release targeting `main`.
2. Install v0.6.0 through HACS (show beta versions if required), then restart HA.
3. Replace the existing dashboard resource URLs, keeping the type **JavaScript module**:
   - `/rotacloud_attendance/static/staff-live.js?v=0.6.0`
   - `/rotacloud_attendance/static/staff-terminal.js?v=0.6.0`
4. Keep one resource entry for each file, then hard-refresh the browser. The new shared module loads automatically; do not add a separate resource for it.
5. Edit your dashboard, use **Add card**, and search **RotaCloud**. Choose Status, Table or Terminal and configure it visually. For each table, select its table type. Existing combined Dashboard/Terminal cards continue to work; there is no need to replace them immediately.
6. To link separate counters/tables, give them the same Filter group in the same view. Keep the combined Dashboard's group blank unless you want it linked too.

Thresholds, age-band break rules, API settings and clocking permissions stay in integration Configure, shared by all cards. A display editor never changes these settings. Backend attendance polling and planning cache policy are unchanged from v0.5.0.

## Validation and rollback

56 offline tests, 27 isolated HA tests and 22 Chromium tests pass. Validated with fictional data in Chromium: existing clocking flows, late/cancelled sessions, duplicate/uncertain writes, picker registrations and visual-editor changes, linked filters/view/preview/integration isolation, columns and sorting, mobile scrolling, Sections grid sizing and resizing widths, click behaviours, shared Refresh/timer cleanup, keyboard input and automatic integration selection. Isolated HA tests cover the added integration metadata. No live HA deployment or real attendance write is performed as part of automated tests.

To roll back, restore v0.5.0, restart HA and restore both module resource URLs to `?v=0.5.0`. New Status/Table card types require v0.6.0: remove them or restore the existing combined Dashboard when rolling back. Existing RotaCloud attendance is unaffected.

References: https://www.home-assistant.io/docs/ ; https://contributors.home-assistant.io/frontend/custom-ui/card/ ; https://contributors.home-assistant.io/frontend/custom-ui/card-editor/
