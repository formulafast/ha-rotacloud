# v0.7.0 — attendance filters and automatic card resources

**HA restart required**, followed by a browser reload. This release changes Python backend code as well as JavaScript. Integration Reload applies configuration changes but does not replace Python modules already loaded in HA. Future release notes will distinguish HA-restart updates from browser-refresh-only changes.

**Before installing:** replace any remaining combined `custom:ff-staff-live` Dashboard with the Status/Table cards introduced in v0.6.0. The combined card is retired and no longer registered or offered in Add card. Remove any old Clocked In / Show All Status card (`status: all`) from your layout too; legacy instances of that counter are hidden rather than turning into duplicate Here counters.

## Status and filtering

- **Here** now counts and filters Here + On Break + Leaving. The underlying staff states/pills still distinguish those three states. Previous-day open clockings remain in their separate table and outside today's counts, as before.
- There is no Clocked In / Show All counter or status-picker choice.
- No selected Status card means no status filter. Clicking a Status card selects it; clicking it again deselects it and restores all rows for that table type. Switching to another card selects that status instead.
- Existing group, view, integration and preview isolation remain in place. Linked tables show all rows when no Status card is selected, even if an older Default filter was saved. Default filter is used only when Respond to linked Status cards is turned off.
- Nothing selected shows all applicable rows in each table: Live still excludes previous-day open records, planning tables still show their own type, and Yesterday still shows older open records only.

## Table exclusion

New checkbox: **Exclude Staff already Scheduled/Here** (default off).

When enabled, hide staff with a shift scheduled today (including a shift already finished), or who are currently clocked in (Here, On Break or Leaving). This is particularly useful on the Availability table. It affects only that table and does not change API data, staff attendance, other tables or global Status counters. Matching uses integration-scoped staff keys, not names; duplicate names are handled independently. Missing staff directory/attendance data is not used to invent an exclusion. Breaks, leave labels, configured columns, sorting, hide-empty and Sections sizing remain supported.

## Terminal

- **Start Break:** green button, play icon.
- **End Break:** yellow button with dark text, pause icon.
- Existing PIN behaviour, clocking permissions and duplicate/uncertain-write protections are unchanged.

## Automatic resources

At integration setup/reload, register or update:

- `/rotacloud_attendance/static/staff-live.js?v=0.7.0`
- `/rotacloud_attendance/static/staff-terminal.js?v=0.7.0`

No manual resource editing is required for the normal UI-managed resource setup. The existing entry IDs are reused and duplicates of these exact local paths are removed. Other cards, external URLs, arbitrary inline resources and dashboard layouts are untouched. Persisted resources are loaded before any change, and concurrent setup calls share a lock. A repeat reload with the right resources already installed makes no resource writes. The shared JavaScript module loads automatically.

If resources are managed in YAML, the integration does not edit the YAML. A Repair supplies the versioned URLs instead. Registration errors also produce a Repair, leaving attendance usable; reload the integration to retry after resolving the problem. No retry polling loop is added.

## Proper versions in HA / Marketplace

Marketplace version display comes from the installed GitHub release or branch, not from card JavaScript. All existing releases were pre-releases, so with Pre-release disabled Marketplace can follow the default branch and display a short commit hash. A version in manifest.json alone cannot relabel a branch installation.

This release adds `hide_default_branch` for HACS/Marketplace's version picker, an `integration_version` attribute on the existing Present metadata sensor, and CI checks that align the release tag, manifest version, running version and imported shared-module cache keys. No extra entity or polling is added. CI also checks the published release tag. It does not publish a release automatically or change Marketplace's saved installation metadata.

### Upgrade and select the release

1. Merge this PR and publish GitHub release **v0.7.0**, targeting `main`. You can keep it a pre-release for the pilot.
2. For a pre-release in the built-in Marketplace, open **Settings > Devices & services > Marketplace**, select the RotaCloud repository device, enable its disabled **Pre-release** switch entity if needed, and turn that switch on. In older HACS, use Show beta versions.
3. Refresh the repository information and use the repository menu's version/download selection to explicitly install **v0.7.0**, rather than `main`/the default branch. Once installed by release tag, Installed version should show v0.7.0 (or its normalised equivalent), not a commit hash. If publishing a regular release instead, the pre-release switch is unnecessary.
4. Restart HA to load the changed backend. Existing UI-managed resources are updated automatically. Do not add another resource entry.
5. Reload the browser (hard-refresh if it retains an older card). Use Add card > RotaCloud to add Status/Table/Terminal cards as needed. Existing modular card configurations remain valid.
6. Check Here, select/deselect filters, and optionally enable the exclusion checkbox on planning tables. Compare the display with RotaCloud. The new Start/End Break styling does not change the actions they send.

If a hash remains, confirm Marketplace has actually installed the release rather than the branch; restarting HA cannot change that selection. The running backend version is also available as `integration_version` on the existing count sensor whose `rotacloud_status` attribute is `present`.

## API and performance

No new API endpoint, per-person lookup, scheduled polling, helper or entity. The checkbox uses existing cached staff/shift/attendance data. Planning TTLs, configured attendance polling and server Refresh cooldowns remain unchanged. Cards retain a shared local minute timer with hidden-page skipping and cleanup. Automatic resource management runs only on setup/reload and is idempotent.

## Validation and rollback

58 offline tests, 32 isolated HA 2026.11.3 tests and 27 Chromium tests cover existing terminal safeguards, Here aggregation, selection toggling, exclusion with duplicate names, retired cards, button icons/colours, Sections/mobile layouts, no-request rendering, shared timers, persisted resource preservation, duplicate/concurrent registration, YAML mode, failure/recovery and release-version consistency. Tests use fictional attendance; no real clocking writes or live HA deployment are performed.

To roll back, install v0.6.0 and restart HA, then manually restore both resource URLs to `?v=0.6.0` and reload the browser. v0.6.0 does not automatically register resources. Its Here filter again excludes breaks/leaving, and its original combined Dashboard becomes available again. Removing the checkbox from a saved Table configuration is optional: older code ignores it. Real RotaCloud attendance is unaffected.

References: https://www.home-assistant.io/docs/ ; https://contributors.home-assistant.io/marketplace/guides/integrations/ ; https://contributors.home-assistant.io/marketplace/guides/releases/ ; https://contributors.home-assistant.io/marketplace/reference/hacs-json/ ; https://contributors.home-assistant.io/frontend/custom-ui/resources/
