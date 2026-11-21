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
4. **Redirect Inspection**: HTTP client redirects (`301`, `302`, `307`, `308`) are manually intercepted and each hop re-verified against the SSRF validator to prevent DNS rebinding or redirect-to-metadata attacks.

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
