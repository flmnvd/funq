import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.parametrize("config_name", [None, "claude-desktop-config.example.json", "claude-code-config.example.json"])
def test_stdio_roundtrip(fake, funq_root, tmp_path, config_name):
    async def run():
        root = Path(__file__).resolve().parents[1]
        script = root / "run_server.py"
        args = ["-B", str(script), "--funq-root", str(funq_root), "--artifact-dir", str(tmp_path)]
        if config_name:
            entry = json.loads((root / config_name).read_text(encoding="utf-8"))["mcpServers"]["funq"]
            assert entry.get("type", "stdio") == "stdio"
            # Relocate the supplied Windows example to this test environment.
            # Keep its argument layout so missing flags or launch changes fail.
            args = list(entry["args"])
            args[1] = str(script)
            args[args.index("--funq-root") + 1] = str(funq_root)
            args[args.index("--artifact-dir") + 1] = str(tmp_path)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        params = StdioServerParameters(command=sys.executable,
                                       args=args, env=env, cwd=str(tmp_path))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                assert "never automatically replay" in init.instructions.lower()
                tools = (await client.list_tools()).tools
                assert len(tools) == 16
                assert next(t for t in tools if t.name == "funq_inspect").annotations.readOnlyHint
                assert not next(t for t in tools if t.name == "funq_click").annotations.readOnlyHint
                attach = await client.call_tool("funq_attach", {"port": fake.port, "expected_class": "CMainWindow"})
                assert not attach.isError
                assert json.loads(attach.content[0].text) == attach.structuredContent
                sid = attach.structuredContent["data"]["session_id"]
                click = await client.call_tool("funq_click", {"session_id": sid, "selector": {"object_name": "apply"}})
                assert click.structuredContent["data"]["verification_required"]
                screenshot = await client.call_tool("funq_screenshot", {"session_id": sid})
                assert screenshot.content[1].type == "image"
                assert screenshot.content[1].mimeType == "image/png"
                assert "image_base64" not in screenshot.structuredContent["data"]
                assert json.loads(screenshot.content[0].text) == screenshot.structuredContent
                missing = await client.call_tool("funq_find", {"session_id": sid, "selector": {"object_name": "missing"}})
                assert missing.isError
                assert missing.structuredContent["error"]["code"] == "ObjectNotFound"
                assert json.loads(missing.content[0].text) == missing.structuredContent
                invalid = await client.call_tool("funq_find", {"session_id": sid, "selector": {"oid": 42}})
                assert invalid.isError
                assert not (await client.call_tool("funq_detach", {"session_id": sid})).isError
    asyncio.run(run())
