# FishFish desktop applications

Three small desktop apps with shared cross-platform logic and seven language files. Windows is the initial supported distribution; Python and Tkinter keep the core portable, but macOS packaging and platform behavior are not yet implemented or tested.

- **Work Motivator:** configure a schedule and hourly wage in Settings. The main view shows the shift status, millisecond countdown, estimated earnings, current rate, and progress. Monthly hours count only time observed while the app is running during scheduled hours; closed or sleeping time is not inferred. Earnings are schedule-based estimates and exclude breaks, taxes, and overtime. An end time earlier than the start is treated as the next day; equal start and end times are invalid. Overnight earnings belong to the shift starting on the previous day after midnight.
- **Three Doors Problem (Monty Hall Problem):** run an experiment of up to 100,000 trials with either strategy, or play 1–20 interactive rounds. With **Save live-game data locally** checked, choose a new `three-door-time-<timestamp>.txt` session record before play; the separately generated `-doors.txt` file records all randomized prize and empty-door assignments before the game starts. Each played round is appended to the session record. With the checkbox unchecked, no live-game record, door-layout file, or live-game history is saved; the in-memory results remain visible until the app closes. The save choice is fixed for a session and does not erase earlier records. The initial selection is random; the host opens an empty door, and the player chooses to switch or stay. The latest 50 experiment runs and, when saving is enabled, live rounds are recorded locally under `%APPDATA%/fishfish/monty-hall/history.json` and shown in the history tabs. Email functionality has been removed.

- **War3 Battle Platform:** an experimental discovery bridge and TCP relay for Classic Warcraft III (Reign of Chaos/Frozen Throne 1.21–1.29). It does not create a VPN or operate a relay server. The host creates a LAN game; each joining player enters the host’s reachable IPv4 address and matching edition/version, starts the bridge, and joins through Warcraft III’s LAN menu. Each player needs their own compatible game installation and matching game version.

  For players on different networks, use an existing VPN that routes IPv4 between players, or configure the host’s router and Windows firewall to forward inbound UDP 6112 and the game’s announced TCP game port to the host PC. Direct public IPv4 may be unavailable behind carrier-grade NAT. The bridge handles discovery broadcasts on the joining player’s machine, but does not bypass NAT, provide authentication, or encrypt direct traffic. Use a trusted network or VPN. The host's game must be running and its LAN lobby active. Only one discovered host lobby is bridged at a time. Close the bridge after play. Actual compatibility and firewall behavior need testing using two Windows computers and the target Warcraft III patch.

All apps provide language, theme, and update controls in the top-left Settings menu. They offer English, Simplified Chinese, Korean, Japanese, Thai, German, and Spanish, as well as light and dark themes. Their theme and language preferences are saved per app. Shared desktop requirements for future apps are documented in `.agents/skills/fishfish-desktop/SKILL.md`.

## Run from source

Install Python 3.10 or later with Tkinter, then run from the repository root:

```sh
python apps/work-motivator/main.py
python apps/monty-hall/main.py
python apps/war3-battle-platform/main.py
python -m unittest discover -s tests -v
```

No runtime packages outside Python's standard library are required. Preferences are stored per app under `%APPDATA%/fishfish/` on Windows. Translations are in `shared/locales/` and the language selector switches the interface immediately.

## Windows builds and updates

The Windows GitHub Actions workflow runs tests and packages a standalone executable, a portable ZIP, and SHA-256 checksum files. Extract the ZIP to a writable folder before running it. A tag like `work-motivator-v1.0.0` or `monty-hall-v1.0.0` creates a separate GitHub release for that app. The tag must match the corresponding version in `shared/common.py`.

Packaged Windows builds check for updates on startup and through **Check for updates**. The updater searches stable release tags for the current app, prompts before downloading, restricts download URLs to GitHub and its release-asset hosts, and verifies the executable size, x64 PE header, SHA-256 checksum, and GitHub digest when available. It stages the executable and a helper beside the app, waits for the running process to exit, creates an `.exe.backup`, replaces the executable, and restarts it. If starting the replacement fails, it attempts to restore the backup. Settings are stored separately and preserved. The app folder must be writable. Checks require a public repository and internet access and are subject to GitHub API rate limits. It scans at most the first 500 releases; a dedicated per-app feed will be needed as the catalog grows. A checksum is not a publisher signature and cannot protect against a compromised release account. Store builds must follow their marketplace's update and signing rules.

The current UI uses Tkinter; platform-dependent packaging and OS integrations belong at the application boundary. No macOS release is promised until its packaging, signing, and behavior have been implemented and tested.
