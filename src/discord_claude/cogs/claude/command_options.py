from discord.commands import OptionChoice

CHAT_MODEL_CHOICES = [
    OptionChoice(name="Claude Opus 4.6", value="claude-opus-4-6"),
    OptionChoice(name="Claude Sonnet 4.6", value="claude-sonnet-4-6"),
    OptionChoice(name="Claude Mythos Preview", value="claude-mythos-preview"),
    OptionChoice(name="Claude Opus 4.5", value="claude-opus-4-5"),
    OptionChoice(name="Claude Sonnet 4.5", value="claude-sonnet-4-5"),
    OptionChoice(name="Claude Opus 4.1", value="claude-opus-4-1"),
    OptionChoice(name="Claude Haiku 4.5", value="claude-haiku-4-5"),
]

RESPONSE_EFFORT_CHOICES = [
    OptionChoice(name="Low", value="low"),
    OptionChoice(name="Medium", value="medium"),
    OptionChoice(name="High", value="high"),
]

TOOL_CHOICE_CHOICES = [
    OptionChoice(name="Auto", value="auto"),
    OptionChoice(name="None", value="none"),
]

__all__ = [
    "CHAT_MODEL_CHOICES",
    "RESPONSE_EFFORT_CHOICES",
    "TOOL_CHOICE_CHOICES",
]
