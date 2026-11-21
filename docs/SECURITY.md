# Security Architecture & Safeguards

The Agent Acquisition Engine enforces defense-in-depth across the acquisition lifecycle.

## 1. SSRF & DNS Protection
Because agents provide arbitrary URLs, Server-Side Request Forgery (SSRF) is the primary attack vector.
The engine protects against SSRF via:
1. **URL Scheme Whitelist**: Only `http://` and `https://` schemes are accepted. Raw schemes like `file://`, `gopher://`, `dict://`, `ftp://` are rejected at the input boundary.
2. **DNS Resolution Verification**: Before issuing any network socket call, the domain is resolved via DNS to obtain its IP addresses.
3. **Private IP Range Enforcement**: If any resolved IP belongs to reserved, private, or loopback ranges, the request is immediately aborted:
   - `127.0.0.0/8` (Loopback)
   - `10.0.0.0/8` (RFC 1918 Private)
   - `172.16.0.0/12` (RFC 1918 Private)
   - `192.168.0.0/16` (RFC 1918 Private)
   - `169.254.0.0/16` (Link-local / AWS & GCP cloud metadata `169.254.169.254`)
   - `::1/128` (IPv6 Loopback)
   - `fc00::/7` (IPv6 Unique Local)
   - `fe80::/10` (IPv6 Link-local)
4. **Direct HTTP Redirect Inspection**: The direct HTTP provider manually intercepts redirects (`301`, `302`, `303`, `307`, `308`), caps redirect hops, and re-verifies each destination against the SSRF validator. DNS results are not pinned to the socket connection, and other providers have their own network clients; production deployments must enforce outbound network restrictions.

## 2. Resource Exhaustion & Denial of Service
- **Maximum File Size**: Strict hard limit of 500 MB (configurable). Streaming stops and the connection terminates immediately if total bytes read exceed this limit.
- **Bounded Download Timeouts**: Per-job timeout (default 300s) prevents hung worker connections.
- **Worker Pool Limits**: Concurrency limits prevent process starvation.

## 3. Storage & Path Traversal Immunity
- **Safe Filenames**: Content-Disposition and URL-derived filenames are sanitized using regex stripping (`[^a-zA-Z0-9._-]`), path traversal markers (`../`, `..\\`) are stripped, and a unique UUID is prepended to ensure non-collision.
- **Private Artifact Access**: Storage files are stored in an isolated internal directory (`storage/artifacts/`). Direct filesystem paths are never returned to agents.

## 4. Expiring Signed Delivery URLs
Artifact downloads require an HMAC-SHA256 signature containing:
- `artifact_id`
- `expires_at` (Unix timestamp, default 3600 seconds)
- Cryptographic signature calculated using `SECRET_KEY`.
Expired or tampered URLs are rejected with HTTP 403 Forbidden.

## 5. File Verification & Malicious Content
1. Non-zero byte check.
2. Content-Length check vs actual downloaded bytes.
3. Magic byte signature validation (ensuring a `.pdf` actually begins with `%PDF-`, PNG with `\x89PNG`, etc.).
4. SHA-256 hash calculated continuously during streaming.
5. Downloaded files are never executed.

## 6. User and Agent Credentials
- Production API requests require authentication; the anonymous development fallback is disabled outside development and test environments.
- Agent API keys are stored as hashes, scoped to one user, and limited to their assigned `read` and `acquire` permissions. Agent keys cannot approve requests, manage portal credentials, or retrieve a user's portal token.
- Approval records are bound to their owner, source, and format. The owner must make the approval decision through a portal credential.
- Production deployments must set a unique `SECRET_KEY` of at least 32 characters. Keep agent keys and portal credentials out of source control, tool arguments, and logs.
