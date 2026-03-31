import asyncio

import aiohttp
from anthropic import APIConnectionError, APIError, AsyncAnthropic

from discord_claude.config.auth import ANTHROPIC_API_KEY


def build_claude_client(api_key: str | None = None) -> AsyncAnthropic:
    """Construct the Anthropic SDK client for the configured API key."""
    return AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)


def build_anthropic_client(api_key: str | None = None) -> AsyncAnthropic:
    """Backward-compatible alias for the Claude client factory."""
    return build_claude_client(api_key)


async def get_http_session(cog) -> aiohttp.ClientSession:
    """Get or lazily create the shared aiohttp session for attachment fetching."""
    if cog._http_session and not cog._http_session.closed:
        return cog._http_session
    async with cog._session_lock:
        if cog._http_session is None or cog._http_session.closed:
            cog._http_session = aiohttp.ClientSession()
        return cog._http_session


def close_http_session(cog) -> None:
    """Close the shared aiohttp session when the cog unloads."""
    loop = getattr(cog.bot, "loop", None)
    session = cog._http_session
    if session and not session.closed:
        if loop and loop.is_running():
            loop.create_task(session.close())
        else:
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(session.close())
            finally:
                new_loop.close()
    cog._http_session = None


__all__ = [
    "APIConnectionError",
    "APIError",
    "AsyncAnthropic",
    "build_claude_client",
    "build_anthropic_client",
    "close_http_session",
    "get_http_session",
]
