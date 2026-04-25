
import os
import io
import json
import discord
import random
from discord.ext import commands
from dotenv import load_dotenv
from gamble import send_gamble_panel, load_gamble_database, save_gamble_database
from acronym import acronym, unacronym, load_acronym_database, save_acronym_database, get_matching_acronym
from llm import chat, summarize_text
from db import init_db, close_db, extract_collection_json, bulk_upload_collection, get_user_balance, set_user_balance, validate_bulk_password, validate_bulk_target
from race_ui import RaceHistoryView, RacePanelView, build_race_embed, build_race_history_embed
from racer_ui import RacersPanelView, build_racers_embed

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
    "extract",
    "upload",
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
    "help"
}
HELP_MESSAGE = (
  "**CatGPT Commands**\n"
  "- `catgpt <message>`: Ask CatGPT a question.\n"
  "- `catgpt summarize` or `catsum`: Reply to a message to summarize it.\n"
  "- `lex <word>`: Alphabetically sorts letters in the word.\n"
  "- `acro <phrase>`: Creates/stores an acronym for a word or phrase.\n"
  "- `unacro <phrase>`: Removes a stored acronym for a word or phrase.\n"
  "- `extract <target>`: Exports DB data as JSON (`acro`, `gamble`, `balances`, `racers`, `race_history`) if you are Blouis.\n"
  "- `upload <target>`: Bulk imports JSON (`acro`, `gamble`, `balances`, `racers`, `race_history`) if you are Blouis.\n"
  "- `roll`: Rolls a random number from 1 to 1000.\n"
  "- `bank [username]`: Shows your balance or another user's balance.\n"
  "- `stim <username> <$amount>`: Adds money to a user's balance (Blouis only).\n"
  "- `racer`: Opens your racers UI (alias of `racers`).\n"
  "- `racers`: Opens your racers UI (create racer + form by index).\n"
  "- `race`: Opens the race panel.\n"
  "- `race history`: Shows last 10 races with details button.\n"
  "- `gamble`: Opens the gambling panel.\n"
  "- `say hi`: Bot says hello.\n"
  "- `cat`: Sends the cat gif.\n"
  "- `blouis`: Sends the Blouis image.\n"
  "- `redward`: Sends the Redward image.\n"
  "- `help`: Shows this command list."
)

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
  if content_lower not in {"catgpt summarize", "catsum"}:
    return False

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
  if content_lower.startswith("catgpt") and not content_lower.startswith("catgpt summarize"):
    await msg.reply(await chat(msg))
    return True
  return False


async def handle_lex_command(msg):
  if msg.content.startswith("lex"):
    await msg.reply(alphabetize(msg.content[3:]))
  return False


async def handle_extract_command(msg):
  if not msg.content.startswith("extract"):
    return False

  parts = msg.content[7:].lower().strip().split()
  if len(parts) < 1:
    await msg.reply("Usage: extract <target> (targets: acro, gamble, balances, racers, race_history)")
    return True

  extract_target = parts[0]

  try:
    extract_target = validate_bulk_target(extract_target)
    validate_bulk_password(msg.author.id)
  except ValueError as e:
    await msg.reply(f"❌ {e}")
    return True

  try:
    json_payload, export_filename = extract_collection_json(extract_target)
    export_file = discord.File(
      fp=io.BytesIO(json_payload.encode("utf-8")),
      filename=export_filename
    )
    await msg.reply(f"Here is your {extract_target} database export.", file=export_file)
  except Exception as e:
    await msg.reply(f"Failed to export data: {e}")
  return True


async def handle_upload_command(msg):
  if not msg.content.startswith("upload"):
    return False

  parts = msg.content[6:].lower().strip().split()
  if len(parts) < 1:
    await msg.reply("Usage: upload <target> (targets: acro, gamble, balances, racers, race_history; attach JSON)")
    return True

  upload_target = parts[0]

  try:
    upload_target = validate_bulk_target(upload_target)
    validate_bulk_password(msg.author.id)
  except ValueError as e:
    await msg.reply(f"❌ {e}")
    return True

  if not msg.attachments:
    await msg.reply("Please attach a JSON file to upload.")
    return True

  attachment = msg.attachments[0]
  if not attachment.filename.endswith('.json'):
    await msg.reply("File must be a JSON file (.json)")
    return True

  try:
    file_content = await attachment.read()
    data = json.loads(file_content.decode('utf-8'))

    result = bulk_upload_collection(upload_target, data)
    await msg.reply(f"✅ {upload_target}: {result}")

    load_database()
  except json.JSONDecodeError:
    await msg.reply("❌ Invalid JSON file format.")
  except ValueError as e:
    await msg.reply(f"❌ Data validation error: {e}")
  except Exception as e:
    await msg.reply(f"❌ Upload failed: {e}")
  return True


async def handle_acro_command(msg, protected_phrases):
  if not msg.content.startswith("acro"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  acro_input = msg.content[4:].lower().strip()
  if acro_input in protected_phrases:
    await msg.reply("You can't acro bot commands.")
  elif acro_input:
    try:
      created_acronym = acronym(str(msg.guild.id), acro_input)
      await msg.reply(f"Acronym added: {created_acronym}")
    except ValueError as e:
      await msg.reply(str(e))
  else:
    await msg.reply("Usage: acro <word or phrase>")
  return False


async def handle_unacro_command(msg):
  if not msg.content.startswith("unacro"):
    return False

  if msg.guild is None:
    await msg.reply("This command only works in a server.")
    return True

  acro_input = msg.content[6:].lower().strip()
  if acro_input:
    try:
      removed = unacronym(str(msg.guild.id), acro_input)
      if removed:
        await msg.reply(f"Acronym removed: {acro_input}")
      else:
        await msg.reply("No acronym found for that word or phrase.")
    except ValueError as e:
      await msg.reply(str(e))
  else:
    await msg.reply("Usage: unacro <word or phrase>")
  return False


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


async def handle_exact_commands(msg, content_lower):
  match content_lower:
    case "help":
      await msg.reply(HELP_MESSAGE)
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
      if msg.guild is None:
        await msg.reply("The race panel only works in a server.")
      else:
        await msg.reply(embed=build_race_embed(msg.guild.id), view=RacePanelView(msg.guild.id))
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


async def handle_passive_reactions(msg):
  if any(word in msg.content for word in skulls):
    emoji = discord.utils.get(msg.guild.emojis, name='tetoaddressme')
    if emoji:
      await msg.add_reaction(emoji)
    else:
      await msg.add_reaction(':skull:')

  if any(word in msg.content for word in meow):
    await msg.reply(meowSeparate(msg.content))

@client.event
async def on_message(msg):
  if msg.author == client.user:
    return

  content_lower = msg.content.lower().strip()

  if await handle_summary_command(msg, content_lower):
    return

  if await handle_catgpt_chat_command(msg, content_lower):
    return

  command = content_lower.split(maxsplit=1)[0] if content_lower else ""

  prefix_handlers = {
    "lex": handle_lex_command,
    "extract": handle_extract_command,
    "upload": handle_upload_command,
    "acro": lambda current_msg: handle_acro_command(current_msg, protected_acro_phrases),
    "unacro": handle_unacro_command,
    "bank": handle_bank_command,
    "stim": handle_stim_command,
  }

  handler = prefix_handlers.get(command)
  if handler and await handler(msg):
    return

  matched_acronym = get_matching_acronym(str(msg.guild.id), content_lower) if msg.guild else None
  if matched_acronym:
    await msg.reply("The Big " + matched_acronym)

  if await handle_exact_commands(msg, content_lower):
    return

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
