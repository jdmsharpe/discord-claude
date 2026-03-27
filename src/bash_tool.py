import asyncio
import logging

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
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=BASH_TIMEOUT)
        except TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out after {BASH_TIMEOUT} seconds"

        output = ""
        if stdout:
            output += stdout.decode(errors="replace")
        if stderr:
            if output:
                output += "\n"
            output += stderr.decode(errors="replace")

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
