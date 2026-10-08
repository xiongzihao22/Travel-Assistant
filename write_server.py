import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from travel_assistant.files import write_note

mcp = FastMCP("TravelNotes")


@mcp.tool()
def write_file(filename: str, content: str) -> dict:
    """将用户明确要求保存的行程写入新 .md/.txt 文件；不能覆盖已有文件。"""
    return write_note(Path(os.environ.get("OUTPUT_DIR", "output")), filename, content)


if __name__ == "__main__":
    mcp.run(transport="stdio")
