import asyncio
import contextlib
import logging
import shutil

logger = logging.getLogger(__name__)

BASH_TIMEOUT = 30  # seconds
MAX_OUTPUT_LINES = 100


async def execute_bash_command(command: str) -> str:
    """Execute a bash command and return combined stdout + stderr.

    Args:
        command: The shell command to run.

    Returns:
        The command output, or an error message on failure/timeout.
    """
    logger.info(f"Executing bash command: {command[:200]}")
    try:
        shell_executable = next(
            (
                shell
                for shell in ("bash", "bash.exe", "sh", "sh.exe")
                if shutil.which(shell) is not None
            ),
            None,
        )
        if shell_executable is not None and command.lstrip().startswith("python "):
            leading_ws = command[: len(command) - len(command.lstrip())]
            python_args = command.lstrip()[len("python ") :]
            command = (
                f"{leading_ws}if command -v python >/dev/null 2>&1; then "
                f"python {python_args}; "
                f"elif command -v python3 >/dev/null 2>&1; then "
                f"python3 {python_args}; "
                f"else python {python_args}; fi"
            )
        if shell_executable is None:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                shell_executable,
                "-lc",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=BASH_TIMEOUT)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(Exception):
                await process.wait()
            return f"Error: Command timed out after {BASH_TIMEOUT} seconds"

        output = ""
        if stdout:
            output += stdout.decode(errors="replace")
        if stderr:
            if output:
                output += "\n"
            output += stderr.decode(errors="replace")
        output = output.replace("\r\n", "\n")

        if not output:
            return "(no output)"

        # Truncate large outputs
        lines = output.split("\n")
        if len(lines) > MAX_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_OUTPUT_LINES])
            output += f"\n\n... Output truncated ({len(lines)} total lines) ..."

        return output
    except Exception as e:
        return f"Error: {e}"
