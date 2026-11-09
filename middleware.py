from dataclasses import dataclass
from typing import Optional

from db import is_fun_opt_out, is_llm_disabled

# Prefix commands that i_hate_fun users are blocked from using.
FUN_COMMANDS = {"acro", "dict"}
FUN_OPT_OUT_REPLY = "You've opted out of acro/dict. Use `i_love_fun` to opt back in."

LLM_COMMANDS = {"catgpt", "catsum"}

GUILD_ONLY_COMMANDS = {
  "acro", "dict", "unacro", "unacroall", "ban", "unban", "ban_list", "notif",
  "skribbl", "toggle_llm_features", "claim", "blame", "charades", "unclaim",
}
GUILD_ONLY_REPLY = "This command only works in a server."

OWNER_ONLY_REPLIES = {
  **{c: f"Only Blouis can use {c}." for c in ("unacroall", "notif", "skribbl", "toggle_llm_features", "stim")},
  "ban": "Only Blouis can ban phrases.",
  "unban": "Only Blouis can unban phrases.",
}


@dataclass(frozen=True)
class ParsedMessage:
  content_lower: str
  command: str
  fun_opt_out: bool
  # None lets the message proceed; "" blocks it silently.
  block_reply: Optional[str] = None

  @property
  def blocked(self):
    return self.block_reply is not None


def has_ignore_flag(content):
  """A standalone '-c' as the first or last word opts a message out of all bot handling."""
  tokens = content.split()
  if not tokens:
    return False
  return tokens[0].lower() == "-c" or tokens[-1].lower() == "-c"


def _block_reply(msg, command, fun_opt_out, owner_id):
  if fun_opt_out and command in FUN_COMMANDS:
    return FUN_OPT_OUT_REPLY
  if msg.guild is None and command in GUILD_ONLY_COMMANDS:
    return GUILD_ONLY_REPLY
  if command in LLM_COMMANDS and (msg.guild is None or is_llm_disabled(msg.guild.id)):
    return ""
  if command in OWNER_ONLY_REPLIES and msg.author.id != owner_id:
    return OWNER_ONLY_REPLIES[command]
  return None


def parse_message(msg, owner_id):
  """Returns None if the message must be ignored (bot author or '-c' flag), else a ParsedMessage."""
  if msg.author.bot or has_ignore_flag(msg.content):
    return None

  content_lower = msg.content.lower().strip()
  command = content_lower.split(maxsplit=1)[0] if content_lower else ""
  fun_opt_out = is_fun_opt_out(msg.author.id)

  return ParsedMessage(
    content_lower=content_lower,
    command=command,
    fun_opt_out=fun_opt_out,
    block_reply=_block_reply(msg, command, fun_opt_out, owner_id),
  )
