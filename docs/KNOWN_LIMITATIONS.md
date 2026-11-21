# Known Technical Limitations (Phase 1 MVP)

In accordance with product principles, technical limitations are documented transparently:

1. **No DRM or Paywall Bypass**: The engine does not bypass digital rights management, CAPTCHAs, or paywalled services. If a source requires authentication not provided via credentials, it will report `PERMISSION_DENIED`.
2. **Headless Browser Execution Deferred**: In Phase 1, javascript-heavy single-page applications requiring browser execution are unsupported. Direct HTTP downloads require direct resource URLs.
3. **Single-Node Worker Concurrency in SQLite**: When running on SQLite in local dev, database concurrency is limited by SQLite's file locking. Production deployments must use PostgreSQL.
4. **Provider-Dependent Media Support**: Media acquisition is supported only through enabled providers and depends on upstream availability, dependencies, and source permissions. It is not universal.
5. **Private Network Sources Blocked**: Internal LAN hosts and cloud metadata addresses are intentionally unreachable due to strict SSRF defense.
6. **No Universal Format Support**: File types and media formats depend on the selected provider and upstream source. Unsupported formats are rejected; there is no promise that an arbitrary URL or natural-language request is downloadable.
7. **No Natural-Language Intent Planner**: The current MCP tools accept a URL and explicit source/format IDs. A separate agent or intent-resolution layer is needed to turn requests such as “find the PDF report” into a reviewed, user-approved acquisition.
8. **Production User Onboarding**: Production mode requires existing user credentials. A verified signup, invitation, or identity-provider bootstrap flow still needs to be built.
9. **SSRF Defense in Depth**: Application checks validate DNS results and each redirect, but do not pin the resolved IP address to the eventual socket connection. Production deployments should enforce outbound network policy at the host/container/network layer.
