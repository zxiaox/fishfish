# FishFish desktop applications

Two small desktop apps with shared cross-platform logic and seven language files. Windows is the initial supported distribution; Python and Tkinter keep the core portable, but macOS packaging and platform behavior are not yet implemented or tested.

- **Work Motivator:** enter a same-day work schedule and nonnegative hourly wage. Time remaining displays milliseconds; the UI refreshes approximately every 25 ms, subject to OS scheduling. Earnings accrue from the scheduled start until the end, with no breaks, tax, overtime, or currency conversion; the entered wage determines the currency. Before the shift, earnings are zero and the countdown includes time until the end; after the shift, earnings are capped and the countdown is zero. Overnight shifts are not supported.
- **Monty Hall:** simulate one or up to 100,000 trials using a chosen stay/switch strategy. Each trial randomly chooses the prize and initial door; the host opens a non-prize, unchosen door. The table previews 500 records and CSV export contains them all. Each run replaces the previous run. Email opens a draft in the user's configured mail application; the user reviews and sends it. Up to 10 records are included in the draft; for larger runs, export the CSV and attach it manually. A configured email application is required; this program does not send mail directly.

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
