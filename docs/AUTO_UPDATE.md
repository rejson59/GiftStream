# GiftStream for Windows: one app, self-contained updates

## Running

GiftStream ships as a single `GiftStream.exe`. There is no separate launcher or installer. On start the app copies itself into `%LOCALAPPDATA%\GiftStream\versions\<version>`, keeps settings in `%LOCALAPPDATA%\GiftStream` and creates or refreshes the `GiftStream` Start-menu shortcut. The Start menu points at the current application file.

The panel runs in a native GiftStream window with embedded Microsoft Edge WebView2. Installing Python is not required. If WebView2 is missing, GiftStream shows a startup error; the runtime can be downloaded from Microsoft's official page.

## Updates

At startup and then every 30 minutes GiftStream checks the newest GitHub release. An update is downloaded as a new `GiftStream.exe`, verified with SHA-256 and stored in the version directory. If an update is found during startup, GiftStream launches it before showing the window. If the download finishes inside a running Windows app, GiftStream automatically starts the new version and closes the old one. That can briefly interrupt event reception; the TikTok stream itself keeps running, but the app may need to reconnect afterwards. The update bar also has a manual retry button, and **Check for updates** starts a check by hand.

A release contains only `GiftStream.exe` and `checksums.txt`. The workflow `.github/workflows/release-windows.yml` builds the single application file after a `vX.Y.Z` tag is created.

## Data

Settings, presets, the gift catalog and history are stored in `%LOCALAPPDATA%\GiftStream`. The clean-install policy stays in force: a new release never imports data from previous installations.

## Security

The SHA-256 checksum detects corruption or an incomplete download, but it is not a replacement for an Authenticode signature. The file is not signed, so Windows SmartScreen may show a warning.
