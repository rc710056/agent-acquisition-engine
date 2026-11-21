# Known Technical Limitations (Phase 1 MVP)

In accordance with product principles, technical limitations are documented transparently:

1. **No DRM or Paywall Bypass**: The engine does not bypass digital rights management, CAPTCHAs, or paywalled services. If a source requires authentication not provided via credentials, it will report `PERMISSION_DENIED`.
2. **Headless Browser Execution Deferred**: In Phase 1, javascript-heavy single-page applications requiring browser execution are unsupported. Direct HTTP downloads require direct resource URLs.
3. **Single-Node Worker Concurrency in SQLite**: When running on SQLite in local dev, database concurrency is limited by SQLite's file locking. Production deployments must use PostgreSQL.
4. **Media Provider in Phase 2**: Video and audio stream demuxing via `yt-dlp` and `ffmpeg` is planned for Phase 2.
5. **Private Network Sources Blocked**: Internal LAN hosts and cloud metadata addresses are intentionally unreachable due to strict SSRF defense.
