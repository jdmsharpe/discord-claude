from discord.commands import OptionChoice

CHAT_MODEL_CHOICES = [
    OptionChoice(name="Claude Fable 5.1", value="claude-fable-5-1"),
    OptionChoice(name="Claude Fable 5", value="claude-fable-5"),
    OptionChoice(name="Claude Opus 5", value="claude-opus-5"),
    OptionChoice(name="Claude Opus 4.8", value="claude-opus-4-8"),
    OptionChoice(name="Claude Sonnet 5", value="claude-sonnet-5"),
    OptionChoice(name="Claude Opus 4.7", value="claude-opus-4-7"),
    OptionChoice(name="Claude Opus 4.6", value="claude-opus-4-6"),
    OptionChoice(name="Claude Sonnet 4.6", value="claude-sonnet-4-6"),
    OptionChoice(name="Claude Opus 4.5", value="claude-opus-4-5"),
    OptionChoice(name="Claude Sonnet 4.5", value="claude-sonnet-4-5"),
    OptionChoice(name="Claude Haiku 4.5", value="claude-haiku-4-5"),
]

RESPONSE_EFFORT_CHOICES = [
    OptionChoice(name="Low", value="low"),
    OptionChoice(name="Medium", value="medium"),
    OptionChoice(name="High", value="high"),
    OptionChoice(name="Extra High", value="xhigh"),
    OptionChoice(name="Max", value="max"),
]

TOOL_CHOICE_CHOICES = [
    OptionChoice(name="Auto", value="auto"),
    OptionChoice(name="None", value="none"),
]

THINKING_DISPLAY_CHOICES = [
    OptionChoice(name="Summarized", value="summarized"),
    OptionChoice(
        name="Progress updates (Fable 5 / 5.1: live status lines between tool calls, reasoning hidden)",
        value="updates",
    ),
]

__all__ = [
    "CHAT_MODEL_CHOICES",
    "RESPONSE_EFFORT_CHOICES",
    "THINKING_DISPLAY_CHOICES",
    "TOOL_CHOICE_CHOICES",
]
