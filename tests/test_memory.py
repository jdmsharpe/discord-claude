import pytest

from memory import (
    _resolve_safe_path,
    execute_memory_operation,
)


@pytest.fixture(autouse=True)
def use_tmp_memories(tmp_path, monkeypatch):
    """Redirect MEMORIES_BASE_DIR to a temp directory for all tests."""
    monkeypatch.setattr("memory.MEMORIES_BASE_DIR", tmp_path)
    return tmp_path


class TestResolveSafePath:
    """Tests for _resolve_safe_path."""

    def test_valid_path_resolves(self, tmp_path):
        """Normal file path resolves within user dir."""
        target = _resolve_safe_path(123, "/memories/notes.txt")
        assert str(target).startswith(str(tmp_path / "123"))

    def test_path_traversal_blocked(self):
        """Path traversal with ../ is blocked."""
        with pytest.raises(ValueError, match="Path traversal"):
            _resolve_safe_path(123, "/memories/../../etc/passwd")

    def test_relative_traversal_blocked(self):
        """Traversal to another user's directory is blocked."""
        with pytest.raises(ValueError, match="Path traversal"):
            _resolve_safe_path(123, "/memories/../456/secrets.txt")

    def test_empty_path_returns_user_dir(self, tmp_path):
        """Empty path resolves to the user directory."""
        target = _resolve_safe_path(123, "/memories")
        assert target == (tmp_path / "123").resolve()

    def test_strips_memories_prefix(self, tmp_path):
        """The /memories/ prefix is stripped correctly."""
        target = _resolve_safe_path(123, "/memories/subdir/file.txt")
        expected = (tmp_path / "123" / "subdir" / "file.txt").resolve()
        assert target == expected


class TestMemoryView:
    """Tests for the view command."""

    def test_view_empty_directory(self):
        """Returns message when no memory files exist."""
        result = execute_memory_operation(
            user_id=123, tool_input={"command": "view", "path": "/memories"}
        )
        assert "No memory files found" in result

    def test_view_lists_files(self, tmp_path):
        """Lists files in the memory directory."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("hello")
        (user_dir / "todo.txt").write_text("world")

        result = execute_memory_operation(
            user_id=123, tool_input={"command": "view", "path": "/memories"}
        )
        assert "notes.txt" in result
        assert "todo.txt" in result

    def test_view_reads_file_with_line_numbers(self, tmp_path):
        """Reads a file and returns contents with line numbers."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("line one\nline two\nline three")

        result = execute_memory_operation(
            user_id=123,
            tool_input={"command": "view", "path": "/memories/notes.txt"},
        )
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result
        # Should have line numbers
        assert "1\t" in result

    def test_view_nonexistent_file(self):
        """Returns error for nonexistent file."""
        result = execute_memory_operation(
            user_id=123,
            tool_input={"command": "view", "path": "/memories/nope.txt"},
        )
        assert "does not exist" in result

    def test_view_with_range(self, tmp_path):
        """Reads specific line range."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "data.txt").write_text("a\nb\nc\nd\ne")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "view",
                "path": "/memories/data.txt",
                "view_range": [2, 4],
            },
        )
        assert "b" in result
        assert "c" in result
        assert "d" in result


class TestMemoryCreate:
    """Tests for the create command."""

    def test_create_new_file(self, tmp_path):
        """Creates a new file."""
        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "create",
                "path": "/memories/notes.txt",
                "file_text": "Hello world",
            },
        )
        assert "File created successfully" in result
        assert (tmp_path / "123" / "notes.txt").read_text() == "Hello world"

    def test_create_existing_file_fails(self, tmp_path):
        """Refuses to overwrite existing file."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("existing")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "create",
                "path": "/memories/notes.txt",
                "file_text": "new content",
            },
        )
        assert "already exists" in result
        # Original content preserved
        assert (user_dir / "notes.txt").read_text() == "existing"

    def test_create_with_subdirectory(self, tmp_path):
        """Creates parent directories as needed."""
        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "create",
                "path": "/memories/subdir/deep/notes.txt",
                "file_text": "deep content",
            },
        )
        assert "File created successfully" in result
        assert (tmp_path / "123" / "subdir" / "deep" / "notes.txt").exists()


class TestMemoryStrReplace:
    """Tests for the str_replace command."""

    def test_successful_replace(self, tmp_path):
        """Replaces text in a file."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("color: blue\nsize: large")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "str_replace",
                "path": "/memories/notes.txt",
                "old_str": "color: blue",
                "new_str": "color: green",
            },
        )
        assert "has been edited" in result
        assert "color: green" in (user_dir / "notes.txt").read_text()

    def test_old_string_not_found(self, tmp_path):
        """Returns error when old string not found."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("hello world")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "str_replace",
                "path": "/memories/notes.txt",
                "old_str": "not found",
                "new_str": "replacement",
            },
        )
        assert "did not appear verbatim" in result

    def test_multiple_matches_fails(self, tmp_path):
        """Returns error when old string has multiple matches."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("hello\nhello\nworld")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "str_replace",
                "path": "/memories/notes.txt",
                "old_str": "hello",
                "new_str": "hi",
            },
        )
        assert "Multiple occurrences" in result


class TestMemoryInsert:
    """Tests for the insert command."""

    def test_insert_at_beginning(self, tmp_path):
        """Inserts text at the beginning of a file."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("line one\nline two\n")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "insert",
                "path": "/memories/notes.txt",
                "insert_line": 0,
                "new_str": "header",
            },
        )
        assert "has been edited" in result
        content = (user_dir / "notes.txt").read_text()
        assert content.startswith("header")

    def test_insert_at_middle(self, tmp_path):
        """Inserts text after a specific line."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "notes.txt").write_text("line one\nline three\n")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "insert",
                "path": "/memories/notes.txt",
                "insert_line": 1,
                "new_str": "line two",
            },
        )
        assert "has been edited" in result
        lines = (user_dir / "notes.txt").read_text().splitlines()
        assert lines[1] == "line two"


class TestMemoryDelete:
    """Tests for the delete command."""

    def test_delete_existing_file(self, tmp_path):
        """Deletes an existing file."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        file_path = user_dir / "notes.txt"
        file_path.write_text("content")

        result = execute_memory_operation(
            user_id=123,
            tool_input={"command": "delete", "path": "/memories/notes.txt"},
        )
        assert "Successfully deleted" in result
        assert not file_path.exists()

    def test_delete_nonexistent_file(self):
        """Returns error for nonexistent file."""
        result = execute_memory_operation(
            user_id=123,
            tool_input={"command": "delete", "path": "/memories/nope.txt"},
        )
        assert "does not exist" in result


class TestMemoryRename:
    """Tests for the rename command."""

    def test_rename_success(self, tmp_path):
        """Renames a file successfully."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "old.txt").write_text("content")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "rename",
                "old_path": "/memories/old.txt",
                "new_path": "/memories/new.txt",
            },
        )
        assert "Successfully renamed" in result
        assert not (user_dir / "old.txt").exists()
        assert (user_dir / "new.txt").read_text() == "content"

    def test_rename_path_traversal_blocked(self, tmp_path):
        """Rename to path outside user directory is blocked."""
        user_dir = tmp_path / "123"
        user_dir.mkdir()
        (user_dir / "file.txt").write_text("content")

        result = execute_memory_operation(
            user_id=123,
            tool_input={
                "command": "rename",
                "old_path": "/memories/file.txt",
                "new_path": "/memories/../../etc/evil.txt",
            },
        )
        assert "Error" in result


class TestInvalidCommand:
    """Tests for invalid commands."""

    def test_unknown_command(self):
        """Returns error for unknown command."""
        result = execute_memory_operation(user_id=123, tool_input={"command": "unknown"})
        assert "Unknown command" in result

    def test_missing_command(self):
        """Returns error when command is missing."""
        result = execute_memory_operation(user_id=123, tool_input={})
        assert "Unknown command" in result
