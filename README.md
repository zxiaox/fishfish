# FishFish desktop applications

Three small desktop apps with shared cross-platform logic and seven language files. Windows is the initial supported distribution; Python and Tkinter keep the core portable, but macOS packaging and platform behavior are not yet implemented or tested.

- **Work Motivator:** configure a schedule and hourly wage in Settings. The main view shows the shift status, millisecond countdown, estimated earnings, current rate, and progress. Monthly hours count only time observed while the app is running during scheduled hours; closed or sleeping time is not inferred. Earnings are schedule-based estimates and exclude breaks, taxes, and overtime. An end time earlier than the start is treated as the next day; equal start and end times are invalid. Overnight earnings belong to the shift starting on the previous day after midnight. The current Gregorian date, weekday, and Chinese lunar date are shown using the computer’s local date; the lunar date is calculated offline. An optional countdown can be configured in hours, minutes, and seconds (default five hours); it continues while the app is closed and stops at zero.
- **Three Doors Problem (Monty Hall Problem):** run an experiment of up to 100,000 trials with either strategy, or play 1–20 interactive rounds. Choose one of three illustrated hosts; Host 2 is the default and the selection is saved. The Windows sound pack uses prerecorded AI voices for English, Simplified Chinese, and Korean. Japanese, Thai, German, and Spanish use compatible installed Windows text-to-speech voices; the app warns if none is available. Windows voice availability varies, and multiple hosts may share one voice. Enable or mute game sounds from Settings. In each round, choose a door, see the host open an empty door, and decide whether to switch or stay. With **Save live-game data locally** checked, choose a new `three-door-time-<timestamp>.txt` file before play; the precommitted door layouts are written to that file before the first round and results are appended to the same file. With saving unchecked, no live-game text file or persistent live-game history is saved; results remain visible in memory until the app closes. Each history tab displays the most recent 50 entries (experiment runs or individual live rounds).

- **War3 Battle Platform:** an experimental, self-hosted lobby directory and TCP relay for Classic Warcraft III 1.21–1.29. Once configured, the app automatically connects to the shared server, detects locally hosted games, and broadcasts other players’ lobbies into Warcraft III's LAN list. The player hosting the service enables **Run the lobby server on this computer** in Settings; the server generates a certificate and displays its SHA-256 fingerprint. The operator shares their public IPv4 address (or DNS name), server port, and fingerprint with the other players, who enter them once in Settings. Compare the fingerprint through a trusted channel. The service must remain running while anyone uses it. The main screen distinguishes a locally detected game from the count of remote games; use Copy diagnostics to collect scan counters if the game is not found.

  The operator must configure their router and firewall to forward the server TCP port (default 47653) to their computer. The operator needs a publicly reachable address; carrier-grade NAT or other inbound restrictions may prevent hosting. Other players make outbound TCP connections and normally do not need router forwarding. The transport is TLS-encrypted and pinned to the operator's certificate. The server has no player authentication or access controls; anyone who can reach it can list and join advertised games, so use a trusted group and network. The server relays traffic through the operator's connection and is subject to that connection's bandwidth and latency. No cloud service, user account, or recurring service fee is built in. Game announcement bytes, including lobby names, are forwarded unchanged. The platform’s own displayed name uses UTF-8 or a best-effort legacy code page based on the selected language; mixed-language legacy names may still display incorrectly. Actual Warcraft III interoperability, Windows firewall behavior, and real internet/NAT combinations still need two-computer testing; the automated tests use simulated game packets and connections.

### Direct IPv6 connection

In **Settings → Lobby server setup → Direct / port forwarding**, the host checks **Run the lobby server on this computer** and **Enable IPv6 listening on this server**, then confirms. The host can reopen settings and use **Find my IPv6 address** to inspect preferred global IPv6 addresses, and privately share a suitable current address, TCP port and certificate fingerprint with the other player. The other player selects Direct, leaves the server checkbox cleared and enters those values. Both networks need working IPv6. The server's IPv6 listener status and address list do not establish internet reachability; allow inbound TCP on the host's Windows and router IPv6 firewalls and test from the other network. IPv6 addresses can change. IPv4 port forwarding is not required for an IPv6 connection. The server does not authenticate players: restrict inbound firewall access to trusted peer addresses where possible. TLS fingerprint pinning verifies the server, not the players. No firewall rules are modified by the app.

### ZeroTier connection mode

In **Settings → Lobby server setup**, choose **Direct / port forwarding** or **ZeroTier network**. The app keeps the address, port, fingerprint, and server role separately for each mode; existing configurations migrate to Direct. ZeroTier mode uses the same self-hosted lobby server over an independently installed ZeroTier virtual network. It does not install ZeroTier, create an account or network, authorize devices, or guarantee connectivity.

Install ZeroTier on each Windows PC and join and authorize both devices in the same network, following [ZeroTier’s setup guide](https://docs.zerotier.com/quickstart/). In ZeroTier mode, the host checks **Run the lobby server on this computer**, clicks **Check local ZeroTier IPv4**, and shares the relevant IPv4 address, port, and fingerprint with the joiner. If more than one address is shown, select the one for the shared network. The joiner enters those details with the host checkbox cleared. The check only lists active local adapters whose name or description contains ZeroTier; it does not prove the peer is authorized or reachable. Check firewall rules for the active ZeroTier network profile. The host must stay online, and restrictive networks can still block or degrade connections.

All apps provide language, theme, and update controls in the top-left Settings menu. They offer English, Simplified Chinese, Korean, Japanese, Thai, German, and Spanish, as well as light and dark themes. Their theme and language preferences are saved per app. Shared desktop requirements for future apps are documented in `.agents/skills/fishfish-desktop/SKILL.md`.

## Run from source

Install Python 3.10 or later with Tkinter, then run from the repository root:

```sh
python apps/work-motivator/main.py
python apps/monty-hall/main.py
python apps/war3-battle-platform/main.py
python -m unittest discover -s tests -v
```

From source, install `cryptography==44.0.3` to run War3 Battle Platform and `Pillow==12.2.0` to run Three Doors, and `lunar_python==1.4.8` to run Work Motivator; packaged Windows builds include these dependencies. Preferences are stored per app under `%APPDATA%/fishfish/` on Windows. Translations are in `shared/locales/` and the language selector switches the interface immediately.

## Windows builds and updates

The Windows GitHub Actions workflow runs tests and packages a standalone executable, a portable ZIP, and SHA-256 checksum files. Extract the ZIP to a writable folder before running it. A tag like `work-motivator-v1.0.0` or `monty-hall-v1.0.0` creates a separate GitHub release for that app. The tag must match the corresponding version in `shared/common.py`.

Packaged Windows builds check for updates on startup and through **Check for updates**. The updater searches stable release tags for the current app, prompts before downloading, restricts download URLs to GitHub and its release-asset hosts, and verifies the executable size, x64 PE header, SHA-256 checksum, and GitHub digest when available. It stages the executable and a helper beside the app, waits for the running process to exit, creates an `.exe.backup`, replaces the executable, and restarts it. If starting the replacement fails, it attempts to restore the backup. Settings are stored separately and preserved. The app folder must be writable. Checks require a public repository and internet access and are subject to GitHub API rate limits. It scans at most the first 500 releases; a dedicated per-app feed will be needed as the catalog grows. A checksum is not a publisher signature and cannot protect against a compromised release account. Store builds must follow their marketplace's update and signing rules.

The current UI uses Tkinter; platform-dependent packaging and OS integrations belong at the application boundary. No macOS release is promised until its packaging, signing, and behavior have been implemented and tested.

## Application catalog

The local catalog assigns stable IDs to the apps: **A001** Work Motivator, **A002** Three Doors Problem, and **A003** War3 Battle Platform. Existing package slugs and release tags remain unchanged. Run the management page from the repository root:

```sh
python management/server.py
```

Open **http://127.0.0.1:8765/** in a browser. Add, edit, search, and archive applications there; IDs are assigned automatically and archived IDs are not reused. Names, slugs, descriptions, and status are saved in `management/apps.json`; commit that file to share catalog changes with the repository. Versions for existing apps come from `shared/common.py` and are not release verification. New entries are catalog records only: adding one does not create an app, build it, publish it, or allocate a release. Use one catalog server and resolve registry conflicts carefully when merging branches to avoid duplicate IDs. The tool binds only to localhost and has no authentication; it is not ready to expose directly on a public server.
