# Privacy

NPU Scribe is designed for local inference with no telemetry, analytics, crash reporting,
automatic update check, cloud API, or API key. Network access is limited to an explicit
model-acquisition action. Normal processing must pass a network-denied test before release.

User data is ordinary, unencrypted files readable by the Windows account and any backup
or sync software with access. Setup must detect likely OneDrive Desktop redirection and
offer a clearly non-synced local directory before storing recordings. Logs and support
reports exclude text, audio, clipboard contents, usernames, credentials, and personal
absolute paths by default. The user controls history, failed-audio retention, and deletion.
