import asyncio
import json
import subprocess
import sys
import httpx
from urllib.parse import urlparse

async def test_mcp_stdio():
    print("\n[TEST 1] Testing MCP Stdio Connection as a user agent...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "services.mcp_server.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ClaudeDesktopTestClient", "version": "1.0"}
        }
    }
    proc.stdin.write(json.dumps(init_req).encode("utf-8") + b"\n")
    await proc.stdin.drain()

    line = await proc.stdout.readline()
    init_res = json.loads(line.decode("utf-8"))
    assert init_res.get("id") == 1, f"Failed init: {init_res}"
    s_info = init_res["result"]["serverInfo"]
    print(f" -> MCP Handshake: SUCCESS (Server: {s_info['name']} v{s_info['version']})")

    # Initialized notification
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode("utf-8") + b"\n")
    await proc.stdin.drain()

    # List tools
    list_tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    proc.stdin.write(json.dumps(list_tools_req).encode("utf-8") + b"\n")
    await proc.stdin.drain()

    line = await proc.stdout.readline()
    tools_res = json.loads(line.decode("utf-8"))
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    print(f" -> Discovered Tools ({len(tool_names)}): {', '.join(tool_names)}")

    # Execute inspect_source
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "inspect_source",
            "arguments": {"url": "https://arxiv.org/pdf/2301.00001.pdf"}
        }
    }
    proc.stdin.write(json.dumps(call_req).encode("utf-8") + b"\n")
    await proc.stdin.drain()

    line = await proc.stdout.readline()
    call_res = json.loads(line.decode("utf-8"))
    raw_text = call_res["result"]["content"][0]["text"]
    data = json.loads(raw_text)
    print(f" -> Tool 'inspect_source' executed: ID={data['source_id']}, MIME={data['mime_type']}, Provider={data['provider']}")

    proc.terminate()
    await proc.wait()
    print(" -> MCP Stdio Test: 100% PASSED\n")

async def test_mcp_sse_transport():
    print("[TEST 2] Testing Remote MCP SSE Transport (http://127.0.0.1:8000/mcp/sse)...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Connect to SSE stream
        async with client.stream("GET", "http://127.0.0.1:8000/mcp/sse") as resp:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            assert "text/event-stream" in resp.headers.get("content-type", "")
            print(" -> SSE Stream established: 200 OK (text/event-stream)")

            # Read endpoint event
            post_endpoint = None
            async for line in resp.aiter_lines():
                if line.startswith("event: endpoint"):
                    continue
                elif line.startswith("data: "):
                    post_endpoint = line.replace("data: ", "").strip()
                    break

            print(f" -> Negotiated Message Post Endpoint: {post_endpoint}")
            assert post_endpoint is not None, "Missing post endpoint in SSE stream"

        print(" -> Remote MCP SSE Transport Test: 100% PASSED\n")

async def test_rest_api_agent_connections():
    print("[TEST 3] Testing REST API Agent Connections Flow...")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
        # Health check
        h_resp = await client.get("/api/v1/health")
        assert h_resp.status_code == 200
        print(" -> Gateway Health: OK")

        # Create new agent connection
        create_payload = {
            "agent_name": "AutonomousVerificationAgent",
            "permissions": ["read", "acquire", "inspect"]
        }
        c_resp = await client.post("/api/v1/connections", json=create_payload)
        assert c_resp.status_code == 201, f"Failed creating connection: {c_resp.text}"
        conn_data = c_resp.json()
        raw_key = conn_data.get("api_key")
        conn_id = conn_data.get("id")
        print(f" -> Created Agent Connection: ID={conn_id}, Name={conn_data['agent_name']}")
        print(f" -> Issued Secure API Key: {raw_key[:12]}... (length={len(raw_key)})")

        # List connections
        l_resp = await client.get("/api/v1/connections")
        assert l_resp.status_code == 200
        conns = l_resp.json()
        assert any(c["id"] == conn_id for c in conns)
        print(f" -> Verified Agent Connection in registry (total active connections: {len(conns)})")
        print(" -> REST API Agent Connections Test: 100% PASSED\n")

async def main():
    print("==================================================================")
    print("       AGENT ACQUISITION ENGINE - END-TO-END CONNECTION TEST      ")
    print("==================================================================")
    await test_mcp_stdio()
    await test_mcp_sse_transport()
    await test_rest_api_agent_connections()
    print("==================================================================")
    print("   ALL USER & AGENT CONNECTION CHANNELS TESTED AND 100% WORKING   ")
    print("==================================================================")

if __name__ == "__main__":
    asyncio.run(main())
