# FishFish desktop applications

Two small desktop apps with shared cross-platform logic and seven language files. Windows is the initial supported distribution; Python and Tkinter keep the core portable, but macOS packaging and platform behavior are not yet implemented or tested.

- **Work Motivator:** configure a schedule and hourly wage in Settings. The main view shows the shift status, millisecond countdown, estimated earnings, current rate, and progress. Monthly hours count only time observed while the app is running during scheduled hours; closed or sleeping time is not inferred. Earnings are schedule-based estimates and exclude breaks, taxes, and overtime. An end time earlier than the start is treated as the next day; equal start and end times are invalid. Overnight earnings belong to the shift starting on the previous day after midnight.
- **Three Doors Problem (Monty Hall Problem):** run an experiment of up to 100,000 trials with either strategy, or play 1–20 interactive rounds. Before a live game begins, choose a new text file to save all randomized prize and empty-door assignments. The player can inspect that file and compare the saved layout with each result. The initial selection is random; the host opens an empty door, and the player chooses to switch or stay. Email functionality has been removed.

Both apps offer English, Simplified Chinese, Korean, Japanese, Thai, German, and Spanish, as well as light and dark themes. Their theme and language preferences are saved per app. Shared desktop requirements for future apps are documented in `.agents/skills/fishfish-desktop/SKILL.md`.

## Run from source

Install Python 3.10 or later with Tkinter, then run from the repository root:

```sh
python apps/work-motivator/main.py
python apps/monty-hall/main.py
python -m unittest discover -s tests -v
```

No runtime packages outside Python's standard library are required. Preferences are stored per app under `%APPDATA%/fishfish/` on Windows. Translations are in `shared/locales/` and the language selector switches the interface immediately.

## Windows builds and updates

The Windows GitHub Actions workflow runs tests and packages a standalone executable, a portable ZIP, and SHA-256 checksum files. Extract the ZIP to a writable folder before running it. A tag like `work-motivator-v1.0.0` or `monty-hall-v1.0.0` creates a separate GitHub release for that app. The tag must match the corresponding version in `shared/common.py`.

Packaged Windows builds check for updates on startup and through **Check for updates**. The updater searches stable release tags for the current app, prompts before downloading, restricts download URLs to GitHub and its release-asset hosts, and verifies the executable size, x64 PE header, SHA-256 checksum, and GitHub digest when available. It stages the executable and a helper beside the app, waits for the running process to exit, creates an `.exe.backup`, replaces the executable, and restarts it. If starting the replacement fails, it attempts to restore the backup. Settings are stored separately and preserved. The app folder must be writable. Checks require a public repository and internet access and are subject to GitHub API rate limits. It scans at most the first 500 releases; a dedicated per-app feed will be needed as the catalog grows. A checksum is not a publisher signature and cannot protect against a compromised release account. Store builds must follow their marketplace's update and signing rules.

The current UI uses Tkinter; platform-dependent packaging and OS integrations belong at the application boundary. No macOS release is promised until its packaging, signing, and behavior have been implemented and tested.
