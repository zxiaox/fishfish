---
name: fishfish-desktop
description: Build, update, package, or release FishFish desktop mini-apps with consistent localization, themes, Windows updater, versions, and application identity. Apply to each application change in this repository.
---

# FishFish desktop applications

For every FishFish app development or update task, read and apply this skill. Reuse `apps/`, `shared/`, and `packaging/` and keep business logic independent of the desktop toolkit and OS where practical. Windows is the supported release platform until macOS packaging and updater behavior are implemented and tested.

- Provide English, Simplified Chinese, Korean, Japanese, Thai, German, and Spanish through `shared/locales/`. Localize user-visible messages, preserve placeholders, and test translations.
- Offer selectable light and dark themes, save the selection per app, and maintain readable contrast. Reuse shared theme support.
- Give each app a distinctive icon; embed the same icon in its Windows executable and use it for the window and taskbar identity. Verify the built app on Windows, including taskbar pinning and restart, when a Windows desktop is available.
- Reuse the shared updater and portable Windows packaging. Preserve settings, require consent before downloading, verify release asset size, checksum and platform, stage replacement with a backup, and allow recovery. A checksum is not a publisher signature. Follow marketplace update and signing rules for store builds.
- For every change intended for users, identify all affected apps, including apps affected through shared code. Advance each affected app's numeric `X.Y.Z` version in `shared/common.py` beyond its latest published release and earlier distributed builds. Source commits and Actions artifacts do not count as updater releases. Test the version comparison and package assets. When release publication is authorized, push one matching tag per affected app (`work-motivator-vX.Y.Z`, `monty-hall-vX.Y.Z`, or the equivalent registered prefix), wait for each tag workflow, and verify each published, non-draft, non-prerelease GitHub Release contains the expected app executable and checksum, and portable ZIP and checksum. Confirm that an earlier version selects the new release. Never reuse a published tag or silently claim an update is available when publication or testing failed. If no release is requested, report the version and release steps rather than silently publishing.
- Run focused tests and the Windows build workflow. Report separately whether package creation, update discovery/download, installation/restart, GUI, and taskbar behavior were verified; do not infer runtime success from a successful build.
