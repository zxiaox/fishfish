---
name: fishfish-desktop
description: Build or modify FishFish desktop mini-apps with consistent localization, themes, Windows packaging, updates, and application identity.
---

# FishFish desktop applications

When adding or changing a FishFish mini-app, reuse the `apps/`, `shared/`, and `packaging/` structure. Keep logic independent of the desktop toolkit and OS wherever practical so macOS support can be added later. Windows is the supported release platform until macOS packaging and updater behavior are implemented and tested.

- Provide English, Simplified Chinese, Korean, Japanese, Thai, German, and Spanish through the existing configuration files in `shared/locales/`. Localize every user-visible message, preserve placeholders, and test translations.
- Offer selectable light and dark themes, save the selection per app, and maintain readable foreground and background contrast. Reuse shared theme support rather than creating incompatible per-app preferences.
- Give each app a distinctive icon. Embed the same icon in its Windows executable and use it for its window and taskbar identity. Test the built executable on Windows, including taskbar pinning and restart behavior.
- Reuse the shared per-app update checker, versioning, portable packaging, and release-tag workflow. The updater must preserve settings, require consent before downloading, validate the update, keep a backup, and allow recovery. GitHub release checks and checksums do not replace publisher signatures; marketplace builds must follow marketplace rules.
- Add focused tests for core behavior and run the Windows build workflow. Explicitly report missing Windows GUI, packaging, icon, or update integration verification.
