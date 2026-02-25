"""Memory tool handler for the Anthropic Memory tool (memory_20250818).

Implements client-side file operations for the memory tool:
view, create, str_replace, insert, delete, rename.

Memory files are stored per-user in: ./memories/{user_discord_id}/
"""

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Base directory for memory files, relative to project root
MEMORIES_BASE_DIR = Path(__file__).parent.parent / "memories"

VALID_COMMANDS = {"view", "create", "str_replace", "insert", "delete", "rename"}


def _resolve_safe_path(user_id: int, file_path: str) -> Path:
    """Resolve a file path within the user's memory directory.

    Raises ValueError if the resolved path escapes the user directory
    (path traversal attack).
    """
    user_dir = MEMORIES_BASE_DIR / str(user_id)
    # Strip leading /memories or /memories/ prefix that Claude sends
    cleaned = file_path.strip()
    if cleaned.startswith("/memories/"):
        cleaned = cleaned[len("/memories/"):]
    elif cleaned.startswith("/memories"):
        cleaned = cleaned[len("/memories"):]
    # Strip leading slashes
    cleaned = cleaned.lstrip("/\\")

    if not cleaned:
        return user_dir

    target = (user_dir / cleaned).resolve()
    user_dir_resolved = user_dir.resolve()

    if not str(target).startswith(str(user_dir_resolved)):
        raise ValueError(
            f"Path traversal detected: {file_path} resolves outside user directory"
        )
    return target


def execute_memory_operation(user_id: int, tool_input: dict[str, Any]) -> str:
    """Execute a memory tool operation and return the result string.

    Always returns a string (never raises). Errors are returned as
    descriptive error strings suitable for tool_result content.
    """
    command = tool_input.get("command", "")
    if command not in VALID_COMMANDS:
        return f"Error: Unknown command '{command}'. Valid commands: {', '.join(sorted(VALID_COMMANDS))}"

    try:
        if command == "view":
            return _handle_view(user_id, tool_input)
        elif command == "create":
            return _handle_create(user_id, tool_input)
        elif command == "str_replace":
            return _handle_str_replace(user_id, tool_input)
        elif command == "insert":
            return _handle_insert(user_id, tool_input)
        elif command == "delete":
            return _handle_delete(user_id, tool_input)
        elif command == "rename":
            return _handle_rename(user_id, tool_input)
        else:
            return f"Error: Unhandled command '{command}'"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.error(f"Memory operation error: {e}", exc_info=True)
        return f"Error: {e}"


def _handle_view(user_id: int, tool_input: dict[str, Any]) -> str:
    """List directory contents or read a file with line numbers."""
    file_path = tool_input.get("path", "/memories")
    target = _resolve_safe_path(user_id, file_path)

    # Auto-create user directory for top-level view
    if not target.exists() and target == _resolve_safe_path(user_id, "/memories"):
        target.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        return f"The path {file_path} does not exist. Please provide a valid path."

    if target.is_dir():
        return _list_directory(target, file_path)

    # Read file with optional view_range
    view_range = tool_input.get("view_range")
    return _read_file(target, file_path, view_range)


def _list_directory(target: Path, display_path: str) -> str:
    """List files and directories up to 2 levels deep."""
    items: list[str] = []
    try:
        for item in sorted(target.rglob("*")):
            # Limit depth to 2 levels
            try:
                relative = item.relative_to(target)
            except ValueError:
                continue
            if len(relative.parts) > 2:
                continue
            # Skip hidden files
            if any(part.startswith(".") for part in relative.parts):
                continue

            size = _human_readable_size(item.stat().st_size) if item.is_file() else "0"
            items.append(f"{size}\t/memories/{relative}")
    except OSError as e:
        return f"Error listing directory: {e}"

    if not items:
        return "No memory files found."

    header = f"Here're the files and directories up to 2 levels deep in {display_path}, excluding hidden items and node_modules:"
    dir_size = _human_readable_size(
        sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    )
    return f"{header}\n{dir_size}\t{display_path}\n" + "\n".join(items)


def _read_file(
    target: Path, display_path: str, view_range: list[int] | None = None
) -> str:
    """Read a file and return contents with line numbers."""
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = target.read_text(encoding="latin-1")

    lines = content.splitlines()

    if len(lines) > 999_999:
        return f"File {display_path} exceeds maximum line limit of 999,999 lines."

    if view_range and len(view_range) == 2:
        start, end = view_range
        start = max(1, start)
        end = min(len(lines), end)
        selected = lines[start - 1 : end]
        start_line = start
    else:
        selected = lines
        start_line = 1

    numbered_lines = []
    for i, line in enumerate(selected, start=start_line):
        numbered_lines.append(f"{i:>6}\t{line}")

    return f"Here's the content of {display_path} with line numbers:\n" + "\n".join(
        numbered_lines
    )


def _handle_create(user_id: int, tool_input: dict[str, Any]) -> str:
    """Create a new file."""
    file_path = tool_input.get("path", "")
    file_text = tool_input.get("file_text", "")

    if not file_path:
        return "Error: 'path' is required for create command."

    target = _resolve_safe_path(user_id, file_path)

    if target.exists():
        return f"Error: File {file_path} already exists"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file_text, encoding="utf-8")
    return f"File created successfully at: {file_path}"


def _handle_str_replace(user_id: int, tool_input: dict[str, Any]) -> str:
    """Replace text in a file."""
    file_path = tool_input.get("path", "")
    old_str = tool_input.get("old_str", "")
    new_str = tool_input.get("new_str", "")

    if not file_path:
        return "Error: 'path' is required for str_replace command."

    target = _resolve_safe_path(user_id, file_path)

    if not target.exists() or target.is_dir():
        return f"Error: The path {file_path} does not exist. Please provide a valid path."

    content = target.read_text(encoding="utf-8")
    count = content.count(old_str)

    if count == 0:
        return f"No replacement was performed, old_str `{old_str}` did not appear verbatim in {file_path}."

    if count > 1:
        # Find line numbers of occurrences
        lines = content.splitlines()
        line_numbers = []
        for i, line in enumerate(lines, start=1):
            if old_str in line:
                line_numbers.append(str(i))
        return f"No replacement was performed. Multiple occurrences of old_str `{old_str}` in lines: {', '.join(line_numbers)}. Please ensure it is unique"

    new_content = content.replace(old_str, new_str, 1)
    target.write_text(new_content, encoding="utf-8")

    # Return a snippet of the edited file
    lines = new_content.splitlines()
    # Find the line where the replacement happened
    replace_line = 0
    for i, line in enumerate(lines):
        if new_str in line:
            replace_line = i
            break

    start = max(0, replace_line - 2)
    end = min(len(lines), replace_line + 3)
    snippet_lines = []
    for i in range(start, end):
        snippet_lines.append(f"{i + 1:>6}\t{lines[i]}")

    return "The memory file has been edited.\n" + "\n".join(snippet_lines)


def _handle_insert(user_id: int, tool_input: dict[str, Any]) -> str:
    """Insert text at a specific line number."""
    file_path = tool_input.get("path", "")
    insert_line = tool_input.get("insert_line", 0)
    new_str = tool_input.get("new_str") or tool_input.get("insert_text", "")

    if not file_path:
        return "Error: 'path' is required for insert command."

    target = _resolve_safe_path(user_id, file_path)

    if not target.exists() or target.is_dir():
        return f"Error: The path {file_path} does not exist"

    content = target.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    n_lines = len(lines)

    if insert_line < 0 or insert_line > n_lines:
        return f"Error: Invalid `insert_line` parameter: {insert_line}. It should be within the range of lines of the file: [0, {n_lines}]"

    new_lines = new_str.splitlines(keepends=True)
    # Ensure the last line has a newline
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    lines[insert_line:insert_line] = new_lines
    target.write_text("".join(lines), encoding="utf-8")
    return f"The file {file_path} has been edited."


def _handle_delete(user_id: int, tool_input: dict[str, Any]) -> str:
    """Delete a file or directory."""
    file_path = tool_input.get("path", "")

    if not file_path:
        return "Error: 'path' is required for delete command."

    target = _resolve_safe_path(user_id, file_path)

    if not target.exists():
        return f"Error: The path {file_path} does not exist"

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return f"Successfully deleted {file_path}"


def _handle_rename(user_id: int, tool_input: dict[str, Any]) -> str:
    """Rename or move a file/directory."""
    old_path = tool_input.get("old_path", "")
    new_path = tool_input.get("new_path", "")

    if not old_path or not new_path:
        return "Error: 'old_path' and 'new_path' are required for rename command."

    old_target = _resolve_safe_path(user_id, old_path)
    new_target = _resolve_safe_path(user_id, new_path)  # Also validates new path

    if not old_target.exists():
        return f"Error: The path {old_path} does not exist"

    if new_target.exists():
        return f"Error: The destination {new_path} already exists"

    new_target.parent.mkdir(parents=True, exist_ok=True)
    old_target.rename(new_target)
    return f"Successfully renamed {old_path} to {new_path}"


def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes}"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}K"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}M"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}G"
