import os
import re
import discord
import random
from discord.ext import commands
from dotenv import load_dotenv
from gambling.gamble import send_gamble_panel, load_gamble_database, save_gamble_database
from acronym import acronym, unacronym, unacronym_by_acronym, unacronym_all_by_author, ban_phrase, unban_phrase, list_banned_phrases, load_acronym_database, save_acronym_database, get_matching_acronym, normalize_reserved_acronym
from dictionary import lookup_acronym, list_all_acronyms, find_acronyms_in_message, blame_acronym, claim_acronym, unclaim_acronym
from dictionaryUI import DictView, build_dict_embed, ClaimSelectView, UnclaimSelectView
from banUI import BanListView, build_ban_list_embed
from helpUI import HelpView, build_help_embed
from llm import chat, summarize_text
from db import (
  init_db, close_db, get_user_balance, set_user_balance,
  set_init_notification, get_init_notification,
  get_enabled_init_notifications, upsert_contributor,
  set_fun_opt_out, is_fun_opt_out,
)
from races.race_ui import RaceHistoryView, RacePanelView, build_race_embed, build_race_history_embed
from races.racer_ui import RacersPanelView, build_racers_embed

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="", intents = intents)
client.add_view(RacePanelView())
client.add_view(RacersPanelView())

def load_database():
  load_gamble_database()
  load_acronym_database()

def save_database():
  save_gamble_database()
  save_acronym_database()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))
    for doc in get_enabled_init_notifications():
      channel = client.get_channel(int(doc['channel_id']))
      if channel is None:
        try:
          channel = await client.fetch_channel(int(doc['channel_id']))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
          continue
      try:
        await channel.send("🐱 CatGPT is up and running!")
      except discord.HTTPException:
        continue

Something = "Hi, I am Catgpt, I respond in meows"
meow = ['meow']
Cat_Gif = "https://tenor.com/view/cat-meow-fat-augh-gif-24948731"
BLOUIS_ID = int(os.getenv("BLOUIS_ID") or "0")
Blouis = "https://media.discordapp.net/attachments/1167731497134985239/1350984991521378455/blouis.png?ex=67da0bd2&is=67d8ba52&hm=137da4b3c04b2aed10ef63a460142ac89999cf6dd84308031a822592eaff4121&=&format=webp&quality=lossless&width=880&height=1174"
Redward = "https://media.discordapp.net/attachments/1167182348664709256/1351370224133472408/IMG_4161.jpg?ex=67da2118&is=67d8cf98&hm=1d3f5982cef9f011aee2f2dcd2d67fc8af18103d5f274414c2acdd108544ee6d&=&format=webp&width=880&height=1172"
alpha = {
    "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0, "g": 0, "h": 0, "i": 0, 
    "j": 0, "k": 0, "l": 0, "m": 0, "n": 0, "o": 0, "p": 0, "q": 0, "r": 0, 
    "s": 0, "t": 0, "u": 0, "v": 0, "w": 0, "x": 0, "y": 0, "z": 0
}
skulls = {"wtf", "wtf?", "weird guy", "💀"}
protected_acro_phrases = {
    "catgpt",
    "lex",
    "acro",
    "unacro",
    "unacroall",
    "roll",
    "bank",
    "stim",
    "racer",
    "racers",
    "race",
    "gamble",
    "say hi",
    "cat",
    "blouis",
    "redward",
    "catsum",
    "dict",
    "claim",
    "blame",
    "unclaim",
    "help",
    "charades",
    "ban",
    "unban",
    "ban_list",
    "notif",
    "i_hate_fun",
    "i_love_fun"
}
reserved_acro_commands = protected_acro_phrases | {"catgpt summarize", "race history"}
reserved_acronyms = {normalize_reserved_acronym(command) for command in reserved_acro_commands}

def alphabetize(word):
    lower_case = word.lower()
    word = list(lower_case)
    word.sort()
    return ''.join(word)

def game():
  sum = random.randint(1,1000)
  return sum

def meowSeparate(msg):
  return msg.replace("meow", "**meow**")


def resolve_stim_target_id(msg, username_arg):
  token = username_arg.strip()
  if token.startswith("<@") and token.endswith(">"):
    token = token[2:-1]
    if token.startswith("!"):
      token = token[1:]

  if token.isdigit():
    return int(token)

  if msg.guild is None:
    if token == msg.author.name or token == msg.author.display_name:
      return msg.author.id
    return None

  lowered = token.lower()
  for member in msg.guild.members:
    if member.name.lower() == lowered or member.display_name.lower() == lowered:
      return member.id
  return None


async def handle_summary_command(msg, content_lower):
  parts = content_lower.split()
  is_catsum_count = len(parts) == 2 and parts[0] == "catsum" and parts[1].isdigit()

  if content_lower not in {"catgpt summarize", "catsum"} and not is_catsum_count:
    return False

  if is_catsum_count:
    count = min(int(parts[1]), 50)
    if count < 10:
      await msg.reply("Mrow? Give me a number between 10 and 50!")
      return True

    fetched = []
    async for m in msg.channel.history(limit=count + 1):
      if m.id == msg.id:
        continue
      if m.author == client.user:
        continue
      if m.content.strip():
        fetched.append(m)
      if len(fetched) >= count:
        break

    fetched.reverse()

    if not fetched:
      await msg.reply("Mew... no messages found to summarize!")
      return True

    formatted = "\n".join(
      f"{m.author.display_name}: {m.content.strip()}" for m in fetched
    )
    await msg.reply(await summarize_text(formatted))
    return True

  if msg.reference is None or msg.reference.message_id is None:
    await msg.reply("Mrow? Reply to a message with `catgpt summarize` or `catsum`, and I'll pounce on a summary.")
    return True

  referenced_message = msg.reference.resolved
  if not isinstance(referenced_message, discord.Message):
    referenced_message = await msg.channel.fetch_message(msg.reference.message_id)

  text_to_summarize = referenced_message.content.strip()
  if text_to_summarize == "":
    await msg.reply("Mew... that message has no text for me to summarize.")
    return True

  if len(text_to_summarize) < 350:
    await msg.reply("Purrhaps too short, human. It's under 350 characters, so no summary this time.")
    return True

  await msg.reply(await summarize_text(text_to_summarize))
  return True


async def handle_catgpt_chat_command(msg, content_lower):
  if not content_lower.startswith("catgpt") or content_lower.startswith("catgpt summarize"):
    return False

  result = await chat(msg)
  action = result.get("action")

  if action == "acro":
    if msg.guild is None:
      await msg.reply("This command only works in a server.")
    elif is_fun_opt_out(msg.author.id):
      await msg.reply("You've opted out of acro/dict. Use `i_hate_fun` to opt back in.")
    else:
      await perform_acro_phrase(msg, result.get("phrase", ""), reserved_acro_commands)
  elif action == "gamble":
    await send_gamble_panel(msg)
  elif action == "race":
    await send_race_panel(msg)
  else:
    await msg.reply(result.get("text") or "Mrow?")

  return True


async def handle_lex_command(msg):
  if msg.content.startswith("lex"):
    await msg.reply(alphabetize(msg.content[3:]))
  return False


async def perform_acro_phrase(msg, phrase, protected_phrases):
  """Creates/stores a single acro phrase and replies. Shared by `acro <phrase>` and CatGPT's agentic acro tool call."""
  acro_input = phrase.lower().strip()
  if acro_input in protected_phrases:
    await msg.reply("You can't acro bot commands.")
  elif acro_input:
    try:
      created_acronym = acronym(
        str(msg.guild.id),
        acro_input,
        str(msg.author.id),
        reserved_acronyms=reserved_acronyms
      )
      await msg.reply(f"Acronym added: {created_acronym}")
    except ValueError as e:
      await msg.reply(str(e))
  else:
    await msg.reply("Usage: acro <word or phrase>")


async def handle_acro_command(msg, protected_phrases):
  if not msg.content.startswith("acro"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if is_fun_opt_out(msg.author.id):
    await msg.reply("You've opted out of acro/dict. Use `i_hate_fun` to opt back in.")
    return True

  acro_input = msg.content[4:].lower().strip()
  if acro_input == "*":
    if msg.author.id != BLOUIS_ID:
      await msg.reply("Only Blouis can use `acro *`.")
      return True

    entries = list_all_acronyms(str(msg.guild.id))
    phrases = []
    seen_phrases = set()
    for _, phrase, _ in entries:
      normalized_phrase = re.sub(r"[^A-Za-z ]", "", phrase)
      normalized_key = normalized_phrase.lower()
      if len(normalized_phrase.replace(" ", "")) <= 1 or not normalized_phrase.strip() or normalized_key in seen_phrases:
        continue
      seen_phrases.add(normalized_key)
      phrases.append(normalized_phrase)
    if not phrases:
      await msg.reply("No acronym phrases found for this server.")
      return True

    chunks = []
    current_chunk = []
    current_length = 0
    for phrase in phrases:
      separator_length = 2 if current_chunk else 0
      if current_chunk and current_length + separator_length + len(phrase) > 2000:
        chunks.append(", ".join(current_chunk))
        current_chunk = []
        current_length = 0
      current_chunk.append(phrase)
      current_length += (2 if len(current_chunk) > 1 else 0) + len(phrase)
    if current_chunk:
      chunks.append(", ".join(current_chunk))

    for chunk in chunks:
      await msg.reply(chunk)
  else:
    await perform_acro_phrase(msg, acro_input, protected_phrases)
  return True


async def handle_dict_command(msg):
  if not msg.content.startswith("dict"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if is_fun_opt_out(msg.author.id):
    await msg.reply("You've opted out of acro/dict. Use `i_hate_fun` to opt back in.")
    return True

  acro_input = msg.content[4:].strip()

  if acro_input == ".":
    try:
      entries = list_all_acronyms(str(msg.guild.id))
      embed = build_dict_embed(msg.guild.id, 0, entries)
      view = DictView(msg.guild.id, page=0, entries=entries)
      await msg.reply(embed=embed, view=view)
    except ValueError as e:
      await msg.reply(str(e))
    return True

  await msg.reply("Usage: dict . (list all)")
  return True


async def handle_unacro_command(msg):
  if not msg.content.startswith("unacro"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  acro_input = msg.content[6:].strip()

  if acro_input == "../":
    bot_msg = None
    acro = None
    async for m in msg.channel.history(limit=20):
      if m.author == client.user:
        if m.content.startswith("The Big "):
          bot_msg = m
          acro = m.content[8:].strip()
          break
        if m.content.startswith("Acronym added: "):
          bot_msg = m
          acro = m.content[15:].strip()
          break

    if bot_msg is None:
      await msg.reply("No `The Big <acro>` or `Acronym added: <acro>` found in the last 20 messages. Can't use `../` here.")
      return True
    try:
      removed = unacronym_by_acronym(str(msg.guild.id), acro, msg.author.id, BLOUIS_ID)
      if removed:
        await msg.reply(f"Acronym removed: {acro}")
      else:
        await msg.reply(f"No acronym found for **{acro}**.")
    except ValueError as e:
      await msg.reply(str(e))
    return True

  acro_input = acro_input.lower()
  if acro_input:
    try:
      removed = unacronym(str(msg.guild.id), acro_input, msg.author.id, BLOUIS_ID)
      if removed:
        await msg.reply(f"Acronym removed: {acro_input}")
      else:
        await msg.reply("No acronym found for that word or phrase.")
    except ValueError as e:
      await msg.reply(str(e))
  else:
    await msg.reply("Usage: unacro <word or phrase>")
  return False


async def handle_unacroall_command(msg):
  if not msg.content.lower().startswith("unacroall"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if msg.author.id != BLOUIS_ID:
    await msg.reply("Only Blouis can use unacroall.")
    return True

  parts = msg.content.split(maxsplit=1)
  if len(parts) != 2:
    await msg.reply("Usage: unacroall <user>")
    return True

  target_user_id = resolve_stim_target_id(msg, parts[1])
  if target_user_id is None:
    await msg.reply("Could not find that user. Use a mention, user ID, username, or display name.")
    return True

  removed_count = unacronym_all_by_author(str(msg.guild.id), target_user_id)
  if removed_count == 0:
    await msg.reply(f"No acronyms found for <@{target_user_id}>.")
  elif removed_count == 1:
    await msg.reply(f"Removed 1 acronym created by <@{target_user_id}>.")
  else:
    await msg.reply(f"Removed {removed_count} acronyms created by <@{target_user_id}>.")
  return True


async def handle_ban_command(msg):
  if not msg.content.lower().startswith("ban"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if msg.author.id != BLOUIS_ID:
    await msg.reply("Only Blouis can ban phrases.")
    return True

  phrase = msg.content[3:].strip()
  if not phrase:
    await msg.reply("Usage: ban <phrase>")
    return True

  try:
    banned, existing_removed = ban_phrase(str(msg.guild.id), phrase)
    if existing_removed:
      await msg.reply(f"🚫 Banned phrase: **{banned}** (existing acronym for it was removed)")
    else:
      await msg.reply(f"🚫 Banned phrase: **{banned}**")
  except ValueError as e:
    await msg.reply(str(e))
  return True


async def handle_unban_command(msg):
  if not msg.content.lower().startswith("unban"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if msg.author.id != BLOUIS_ID:
    await msg.reply("Only Blouis can unban phrases.")
    return True

  phrase = msg.content[5:].strip()
  if not phrase:
    await msg.reply("Usage: unban <phrase>")
    return True

  try:
    removed = unban_phrase(str(msg.guild.id), phrase)
    if removed:
      await msg.reply(f"✅ Unbanned phrase: **{phrase.lower().strip()}**")
    else:
      await msg.reply("That phrase isn't banned.")
  except ValueError as e:
    await msg.reply(str(e))
  return True


async def handle_ban_list_command(msg, content_lower):
  if content_lower != "ban_list":
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  entries = list_banned_phrases(str(msg.guild.id))
  embed = build_ban_list_embed(msg.guild.id, 0, entries)
  view = BanListView(msg.guild.id, page=0, entries=entries)
  await msg.reply(embed=embed, view=view)
  return True


async def handle_notif_command(msg, content_lower):
  if content_lower != "notif":
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  if msg.author.id != BLOUIS_ID:
    await msg.reply("Only Blouis can use notif.")
    return True

  current = get_init_notification(str(msg.guild.id), str(msg.channel.id))
  new_state = not (current and current.get("enabled"))
  set_init_notification(str(msg.guild.id), msg.guild.name, str(msg.channel.id), msg.channel.name, new_state)

  if new_state:
    await msg.reply("🔔 This channel will get a ping when I come online.")
  else:
    await msg.reply("🔕 This channel will no longer get startup pings.")
  return True


async def handle_i_hate_fun_command(msg):
  if not msg.content.lower().startswith("i_hate_fun"):
    return False

  if is_fun_opt_out(msg.author.id):
    await msg.reply("😐 You're already opted out of acro/dict commands and acronym responses.")
    return True

  set_fun_opt_out(msg.author.id, True)
  await msg.reply("😐 You are now opted out of acro/dict commands and acronym responses. Use `i_love_fun` to opt back in.")
  return True


async def handle_i_love_fun_command(msg):
  if not msg.content.lower().startswith("i_love_fun"):
    return False

  if not is_fun_opt_out(msg.author.id):
    await msg.reply("🎉 You're already opted into acro/dict commands and acronym responses.")
    return True

  set_fun_opt_out(msg.author.id, False)
  await msg.reply("🎉 You are opted back into acro/dict commands and acronym responses.")
  return True


async def handle_bank_command(msg):
  if not msg.content.startswith("bank"):
    return False
  parts = msg.content.split(maxsplit=1)
  if len(parts) == 1:
    target_user_id = msg.author.id
  else:
    target_user_id = resolve_stim_target_id(msg, parts[1])
    if target_user_id is None:
      await msg.reply("Could not find that user. Use a mention, user ID, username, or display name.")
      return True

  balance = get_user_balance(target_user_id)
  await msg.reply(f"<@{target_user_id}> has ${balance}.")
  return False


async def handle_stim_command(msg):
  if not msg.content.startswith("stim"):
    return False

  parts = msg.content.split()
  if len(parts) != 3:
    await msg.reply("Usage: stim <username> <$amount>")
    return True

  if msg.author.id != BLOUIS_ID:
    await msg.reply("Only Blouis can use stim.")
    return True

  _, username_arg, amount_arg = parts
  target_user_id = resolve_stim_target_id(msg, username_arg)
  if target_user_id is None:
    await msg.reply("Could not find that user. Use a mention, user ID, username, or display name.")
    return True

  amount_text = amount_arg[1:] if amount_arg.startswith("$") else amount_arg
  try:
    amount = int(amount_text)
  except ValueError:
    await msg.reply("Amount must be an integer. Example: $100")
    return True

  if amount == 0:
    await msg.reply("Amount cannot be 0.")
    return True

  balance = get_user_balance(target_user_id)
  set_user_balance(target_user_id, balance + amount)
  await msg.reply(f"big yahu gave u a stim check of ${amount}")
  return True


async def handle_claim_acro_command(msg):
  if not msg.content.lower().startswith("claim"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  parts = msg.content.split()
  if len(parts) < 2:
    await msg.reply("Usage: `claim <ACRO>` or `claim <ACRO> <user>` (Blouis only)")
    return True

  acro_arg = parts[1]

  if len(parts) >= 3:
    if msg.author.id != BLOUIS_ID:
      await msg.reply("Only Blouis can claim acronyms for other users.")
      return True
    user_arg = " ".join(parts[2:])
    target_user_id = resolve_stim_target_id(msg, user_arg)
    if target_user_id is None:
      await msg.reply("Could not find that user. Use a mention, user ID, username, or display name.")
      return True
  else:
    target_user_id = msg.author.id

  phrases = lookup_acronym(str(msg.guild.id), acro_arg)
  if len(phrases) == 0:
    await msg.reply(f"No acronym **{acro_arg.upper()}** found for this server.")
    return True

  if len(phrases) > 1:
    view = ClaimSelectView(str(msg.guild.id), acro_arg, phrases, target_user_id, msg.author.id)
    await msg.reply(f"**{acro_arg.upper()}** has multiple entries — which phrase do you mean?", view=view)
    return True

  try:
    target_member = msg.guild.get_member(target_user_id)
    display_name = target_member.display_name if target_member else None
    claim_acronym(str(msg.guild.id), acro_arg, target_user_id, display_name=display_name)
    if target_user_id == msg.author.id:
      await msg.reply(f"✅ You claimed **{acro_arg.upper()}**.")
    else:
      await msg.reply(f"✅ Claimed **{acro_arg.upper()}** for <@{target_user_id}>.")
  except ValueError as e:
    await msg.reply(str(e))
  return True


async def handle_blame_acro_command(msg):
  if not msg.content.lower().startswith("blame"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  parts = msg.content.split()
  if len(parts) != 2:
    await msg.reply("Usage: `blame <ACRO>`")
    return True

  acro_arg = parts[1]
  entries = blame_acronym(str(msg.guild.id), acro_arg)
  if not entries:
    await msg.reply(f"No acronym **{acro_arg.upper()}** found for this server.")
    return True

  lines = []
  for phrase, author_id in entries:
    owner = "*(unclaimed)*"
    if author_id:
      member = msg.guild.get_member(int(author_id))
      if member is None:
        try:
          member = await msg.guild.fetch_member(int(author_id))
        except (discord.NotFound, discord.HTTPException, ValueError):
          member = None
      owner = member.display_name if member else "Unknown user"
      if member:
        upsert_contributor(str(msg.guild.id), author_id, member.display_name)
    lines.append(f"**{acro_arg.upper()}** → {phrase} — {owner}")
  await msg.reply("\n".join(lines))
  return True


async def handle_charades_command(msg):
  if not msg.content.lower().startswith("charades"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  parts = msg.content.split()
  count = 3
  if len(parts) >= 2:
    if not parts[1].isdigit():
      await msg.reply("Usage: charades <number>")
      return True
    count = int(parts[1])

  if count < 1:
    await msg.reply("Number must be at least 1.")
    return True

  count = min(count, 10)

  entries = list_all_acronyms(str(msg.guild.id))
  phrases = [phrase for _, phrase, _ in entries if phrase.strip()]
  if not phrases:
    await msg.reply("No acronym phrases found for this server.")
    return True

  selected = random.sample(phrases, min(count, len(phrases)))
  await msg.reply("\n".join(selected))
  return True


async def handle_unclaim_acro_command(msg):
  if not msg.content.lower().startswith("unclaim"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  parts = msg.content.split()
  if len(parts) < 2:
    await msg.reply("Usage: `unclaim <ACRO>` or `unclaim <ACRO> <user>` (Blouis only)")
    return True

  acro_arg = parts[1]

  if len(parts) >= 3:
    if msg.author.id != BLOUIS_ID:
      await msg.reply("Only Blouis can unclaim acronyms for other users.")
      return True
    user_arg = " ".join(parts[2:])
    target_user_id = resolve_stim_target_id(msg, user_arg)
    if target_user_id is None:
      await msg.reply("Could not find that user. Use a mention, user ID, username, or display name.")
      return True
  else:
    target_user_id = msg.author.id

  phrases = lookup_acronym(str(msg.guild.id), acro_arg)
  if len(phrases) == 0:
    await msg.reply(f"No acronym **{acro_arg.upper()}** found for this server.")
    return True

  if len(phrases) > 1:
    view = UnclaimSelectView(str(msg.guild.id), acro_arg, phrases, target_user_id, msg.author.id)
    await msg.reply(f"**{acro_arg.upper()}** has multiple entries — which phrase do you mean?", view=view)
    return True

  try:
    unclaim_acronym(str(msg.guild.id), acro_arg, target_user_id)
    if target_user_id == msg.author.id:
      await msg.reply(f"✅ **{acro_arg.upper()}** has been unclaimed.")
    else:
      await msg.reply(f"✅ Removed claim on **{acro_arg.upper()}** from <@{target_user_id}>.")
  except ValueError as e:
    await msg.reply(str(e))
  return True


async def send_race_panel(msg):
  """Shared by the `race` command and CatGPT's agentic race tool call."""
  if msg.guild is None:
    await msg.reply("The race panel only works in a server.")
    return
  await msg.reply(embed=build_race_embed(msg.guild.id), view=RacePanelView(msg.guild.id))


async def handle_exact_commands(msg, content_lower):
  match content_lower:
    case "help":
      await msg.reply(embed=build_help_embed(0), view=HelpView())
      return False
    case "roll":
      await msg.reply(game())
      return False
    case "gamble":
      await send_gamble_panel(msg)
      return False
    case "racer" | "racers":
      if msg.guild is None:
        await msg.reply("Racers UI only works in a server.")
      else:
        await msg.reply(embed=build_racers_embed(msg.guild.id, msg.author.id, msg.author.display_name), view=RacersPanelView())
      return True
    case "race":
      await send_race_panel(msg)
      return False
    case "race history":
      if msg.guild is None:
        await msg.reply("Race history only works in a server.")
      else:
        await msg.reply(embed=build_race_history_embed(msg.guild.id, 10), view=RaceHistoryView(msg.guild.id))
      return True
    case "say hi":
      await msg.reply(Something)
      return False
    case "cat":
      await msg.reply(Cat_Gif)
      return False
    case "blouis":
      await msg.reply(Blouis)
      return False
    case "redward":
      await msg.reply(Redward)
      return False
    case _:
      return False


async def handle_auto_dict(msg):
  if msg.guild is None:
    return
  if is_fun_opt_out(msg.author.id):
    return
  found = find_acronyms_in_message(str(msg.guild.id), msg.content)
  if not found:
    return
  acro = random.choice(list(found.keys()))
  phrases = found[acro]
  joined = ", or ".join(f"**{p}**" for p in phrases)
  replys = [f"errm, **{acro}** stands for {joined}, it's slang btw <:ermmm:1507526975458377728>",
            f"for those who just joined the chat, **{acro}** is short for {joined}",
            f"btw chat **{acro}** is slang for {joined}"]
  await msg.reply(replys[random.randint(0, len(replys) - 1)])


async def handle_passive_reactions(msg):
  if any(word in msg.content for word in skulls):
    emoji = discord.utils.get(msg.guild.emojis, name='tetoaddressme')
    if emoji:
      await msg.add_reaction(emoji)
    else:
      await msg.add_reaction(':skull:')

  if any(word in msg.content for word in meow):
    await msg.reply(meowSeparate(msg.content))

def has_ignore_flag(content):
  """A standalone '-c' as the first or last word opts a message out of all bot handling."""
  tokens = content.split()
  if not tokens:
    return False
  return tokens[0].lower() == "-c" or tokens[-1].lower() == "-c"


@client.event
async def on_message(msg):
  if msg.author.bot:
    return

  if has_ignore_flag(msg.content):
    return

  content_lower = msg.content.lower().strip()

  if await handle_summary_command(msg, content_lower):
    return

  if await handle_catgpt_chat_command(msg, content_lower):
    return

  command = content_lower.split(maxsplit=1)[0] if content_lower else ""

  prefix_handlers = {
    "lex": handle_lex_command,
    "acro": lambda current_msg: handle_acro_command(current_msg, reserved_acro_commands),
    "unacro": handle_unacro_command,
    "unacroall": handle_unacroall_command,
    "dict": handle_dict_command,
    "bank": handle_bank_command,
    "stim": handle_stim_command,
    "claim": handle_claim_acro_command,
    "blame": handle_blame_acro_command,
    "unclaim": handle_unclaim_acro_command,
    "charades": handle_charades_command,
    "ban": handle_ban_command,
    "unban": handle_unban_command,
    "ban_list": lambda current_msg: handle_ban_list_command(current_msg, content_lower),
    "notif": lambda current_msg: handle_notif_command(current_msg, content_lower),
    "i_hate_fun": handle_i_hate_fun_command,
    "i_love_fun": handle_i_love_fun_command,
  }

  handler = prefix_handlers.get(command)
  if handler and await handler(msg):
    return

  matched_acronym = get_matching_acronym(str(msg.guild.id), content_lower) if msg.guild else None
  if matched_acronym and not is_fun_opt_out(msg.author.id):
    await msg.reply("The Big " + matched_acronym)

  if await handle_exact_commands(msg, content_lower):
    return

  await handle_auto_dict(msg)
  await handle_passive_reactions(msg)

try:
  init_db()
  load_database()
  token = os.getenv("TOKEN") or ""
  if token == "":
    raise Exception("Please add your token to the Secrets pane.")
  client.run(token)
except discord.HTTPException as e:
    if e.status == 429:
        print(
            "The Discord servers denied the connection for making too many requests"
        )
        print(
            "Get help from https://stackoverflow.com/questions/66724687/in-discord-py-how-to-solve-the-error-for-toomanyrequests"
        )
    else:
        raise e
finally:
  save_database()
  close_db()
