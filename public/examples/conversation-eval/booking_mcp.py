"""Test the saved booking rule's instructions inline through the MCP server."""
import asyncio
import json
import os
from pathlib import Path

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client


async def main():
    name = "booking-claim-check"
    messages = json.loads(Path("daniel.json").read_text())
    endpoint = os.getenv("FI_BASE_URL", "https://api.futureagi.com").rstrip("/") + "/mcp"
    headers = {"X-Api-Key": os.environ["FI_API_KEY"], "X-Secret-Key": os.environ["FI_SECRET_KEY"]}
    async with create_mcp_http_client(headers=headers) as http:
        transport = streamable_http_client(endpoint, http_client=http)
        async with Client(transport, mode="legacy", read_timeout_seconds=120) as client:
            async def call(tool, **arguments):
                response = await client.call_tool(tool, arguments)
                if response.is_error:
                    raise RuntimeError(f"{tool} returned an error")
                item = next(item for item in response.content if item.type == "text")
                data = json.loads(item.text)
                return data.get("result", data)

            page = await call("list_eval_templates", search=name, owner_filter="user")
            template_id = next(row["id"] for row in page["items"] if row["name"] == name)
            rule = await call("get_eval_template", template_id=template_id)
            grade = await call(
                "test_evaluation", name=name, criteria=rule["instructions"],
                template_type="Llm", output_type=rule["config"]["output"],
                required_keys=rule["required_keys"], model=rule["model"],
                config={"model": rule["model"], "mapping": {"conversation": messages}},
            )
            if not grade.get("output") or not grade.get("reason"):
                raise RuntimeError("No verdict or explanation returned")
            print(json.dumps({key: grade[key] for key in ("output", "reason")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
