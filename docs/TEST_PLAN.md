# Automated Test Plan & Quality Assurance

All tests are implemented using `pytest` and `pytest-asyncio`.

## Test Matrix

### 1. Unit Tests (`tests/unit/`)
- `test_ssrf_validator.py`: Checks private IP ranges, loopback (`127.0.0.1`, `::1`), link-local (`169.254.169.254`), non-HTTP schemes (`file://`, `ftp://`).
- `test_sanitization.py`: Path traversal characters (`../`, `..\\`), safe filenames, extension preservation.
- `test_state_machine.py`: Verifies valid transitions (`created` -> `queued` -> `downloading` -> `verifying` -> `completed`) and rejects invalid state hops.
- `test_signed_url.py`: Verifies HMAC-SHA256 token generation, expiration enforcement, and tamper detection.
- `test_file_verifier.py`: Magic byte checking for PDF, PNG, JPEG, ZIP, gzip; SHA-256 computation.

### 2. Integration Tests (`tests/integration/`)
- `test_direct_http_provider.py`: Runs against local HTTP mock test server, streams bytes, tests chunk progress callback.
- `test_api_database.py`: Tests user creation, job creation, artifact saving, and foreign key relations.
- `test_worker_lifecycle.py`: Spins up the worker loop, inserts a queued job, verifies state transitions and artifact record creation.

### 3. Security Tests (`tests/security/`)
- `test_ssrf_attacks.py`: Tests attempts to probe localhost ports, cloud metadata endpoints, and DNS rebinding simulations.
- `test_oversized_file_attack.py`: Simulates infinite streaming response; verifies engine aborts when exceeding size threshold.
- `test_tampered_delivery_token.py`: Attempts to download artifacts with altered signatures or expired timestamps.

### 4. End-to-End Tests (`tests/e2e/`)
- `test_mcp_journey.py`:
  1. Authenticates test agent.
  2. Calls `inspect_source` with permitted URL.
  3. Calls `list_formats`.
  4. Calls `preflight_acquisition`.
  5. Calls `start_acquisition`.
  6. Polls `get_job_status` until `completed`.
  7. Calls `get_artifact`.
  8. Fetches binary from signed delivery link and verifies SHA-256.
