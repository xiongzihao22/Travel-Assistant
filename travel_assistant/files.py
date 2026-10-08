import re
from pathlib import Path


def write_note(root: Path, filename: str, content: str) -> dict:
    """Create a new UTF-8 note in one fixed directory; never replace existing files."""
    if (
        not re.fullmatch(r"[\w\-][\w\-. ]{0,79}\.(?:md|txt)", filename)
        or ".." in filename
        or filename.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        return {"error": "仅支持普通 .md/.txt 文件名，不允许路径或系统保留名称。"}
    if not content.strip() or len(content.encode("utf-8")) > 100_000:
        return {"error": "内容不能为空，且不能超过 100 KB。"}
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / filename
    if target.is_symlink() or target.resolve().parent != root:
        return {"error": "文件路径不被允许。"}
    try:
        with target.open("x", encoding="utf-8") as file:
            file.write(content)
    except FileExistsError:
        return {"error": "文件已存在，请选择另一个文件名；不会覆盖原文件。"}
    except OSError:
        return {"error": "保存失败，请检查输出目录权限。"}
    return {"saved": True, "filename": filename, "bytes": len(content.encode("utf-8"))}
