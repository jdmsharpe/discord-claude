class TestExecuteBashCommand:
    """Tests for the execute_bash_command function."""

    async def test_simple_command(self):
        """A simple echo command returns its output."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("echo hello")
        assert "hello" in result

    async def test_stderr_included(self):
        """stderr output is included in the result."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("echo error >&2")
        assert "error" in result

    async def test_combined_stdout_stderr(self):
        """Both stdout and stderr are returned together."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("echo out && echo err >&2")
        assert "out" in result
        assert "err" in result

    async def test_no_output(self):
        """Command with no output returns placeholder text."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("true")
        assert result == "(no output)"

    async def test_timeout(self):
        """Command that exceeds timeout returns error message."""
        from unittest.mock import patch

        from bash_tool import execute_bash_command

        with patch("bash_tool.BASH_TIMEOUT", 0.1):
            result = await execute_bash_command("sleep 10")
        assert "timed out" in result

    async def test_nonexistent_command(self):
        """Running a nonexistent command returns error output."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("nonexistentcommand12345")
        assert "not found" in result or "not recognized" in result

    async def test_output_truncation(self):
        """Output exceeding MAX_OUTPUT_LINES is truncated."""
        from unittest.mock import patch

        from bash_tool import execute_bash_command

        with patch("bash_tool.MAX_OUTPUT_LINES", 5):
            result = await execute_bash_command(
                "python -c \"print('\\n'.join(f'line{i}' for i in range(1, 21)))\""
            )
        assert "truncated" in result.lower()
        assert "line1" in result
        # Lines beyond the limit should not appear
        assert "line20" not in result

    async def test_exit_code_nonzero(self):
        """Non-zero exit code still returns output (stderr)."""
        from bash_tool import execute_bash_command

        result = await execute_bash_command("ls /nonexistent_path_xyz")
        # Should contain error message from ls, not crash
        assert len(result) > 0
