import os
import random
import math
from collections import Counter
import discord
from discord.ext import commands
from gamble_ui import build_gamble_embed, GambleView
from db import gamble_collection, get_user_balance, set_user_balance, get_gamble_leaderboard

roulette_doubler = {}  # In-memory cache of player data
message_cooldown = commands.CooldownMapping.from_cooldown(1.0, 4.0, commands.BucketType.user)
mode = "random"  # Change to "random" for random mode instead of pool mode
pool_pulls = []

OUTCOME_LABELS = {
  "JACKPOT_10X": "10x Jackpot",
  "TRIPLE_WIN": "Triple Win",
  "DOUBLE_WIN": "Double Win",
  "LOSE_ALL": "Lose All",
  "TRIPLE_LOSS": "Triple Loss",
  "DOUBLE_LOSS": "Double Loss",
  "SINGLE_WIN": "Single Win",
  "SINGLE_LOSS": "Single Loss",
}


def _build_pool_pulls():
  jackpot_10x = random.choice([0, 1])
  triple_win = random.randint(0, 2)
  double_win = random.randint(0, 2)
  lose_all = random.choice([0, 1])
  triple_loss = random.randint(0, 2)
  double_loss = random.randint(0, 2)

  special_total = jackpot_10x + triple_win + double_win + lose_all + triple_loss + double_loss
  remaining = max(0, 20 - special_total)

  single_win = remaining // 2 + random.randint(-1, 1)
  single_win = max(0, min(remaining, single_win))
  single_loss = remaining - single_win

  pulls = (
    ["JACKPOT_10X"] * jackpot_10x
    + ["TRIPLE_WIN"] * triple_win
    + ["DOUBLE_WIN"] * double_win
    + ["LOSE_ALL"] * lose_all
    + ["TRIPLE_LOSS"] * triple_loss
    + ["DOUBLE_LOSS"] * double_loss
    + ["SINGLE_WIN"] * single_win
    + ["SINGLE_LOSS"] * single_loss
  )
  random.shuffle(pulls)
  return pulls


def _next_pool_pull():
  global pool_pulls
  if not pool_pulls:
    pool_pulls = _build_pool_pulls()
  return pool_pulls.pop()


def _next_random_pull():
  roll = random.random() * 100

  if roll < 0.5:
    return "LOSE_ALL"
  if roll < 2.5:
    return "TRIPLE_LOSS"
  if roll < 7.5:
    return "DOUBLE_LOSS"
  if roll < 8.0:
    return "JACKPOT_10X"
  if roll < 10.0:
    return "TRIPLE_WIN"
  if roll < 15.0:
    return "DOUBLE_WIN"

  return "SINGLE_LOSS" if random.randint(0, 1) == 0 else "SINGLE_WIN"


def _draw_next_pull():
  if mode == "pool":
    return _next_pool_pull()
  return _next_random_pull()


def _pull_label(pull):
  return OUTCOME_LABELS.get(pull, "Unknown")


def _percent_cost(balance, ratio):
  return max(1, math.ceil(balance * ratio))


def _normalize_player_data(player_data):
  if isinstance(player_data, dict):
    name = str(player_data.get("name", "Unknown"))
    win_streak = player_data.get("win_streak", 0)
    last_amount_change = player_data.get("last_amount_change", 0)
    last_multiplier = str(player_data.get("last_multiplier", "N/A"))
    next_pull = player_data.get("next_pull")
    next_pull_revealed = bool(player_data.get("next_pull_revealed", False))
    guild_ids = player_data.get("guild_ids", [])
  else:
    name = "Unknown"
    win_streak = 0
    last_amount_change = 0
    last_multiplier = "N/A"
    next_pull = None
    next_pull_revealed = False
    guild_ids = []

  try:
    win_streak = int(win_streak)
  except (TypeError, ValueError):
    win_streak = 0

  if win_streak < 0:
    win_streak = 0

  try:
    last_amount_change = int(last_amount_change)
  except (TypeError, ValueError):
    last_amount_change = 0

  if not isinstance(guild_ids, list):
    guild_ids = []

  normalized_guild_ids = []
  seen = set()
  for guild_id in guild_ids:
    gid = str(guild_id).strip()
    if gid and gid not in seen:
      normalized_guild_ids.append(gid)
      seen.add(gid)

  return {
    "name": name,
    "win_streak": win_streak,
    "last_amount_change": last_amount_change,
    "last_multiplier": last_multiplier,
    "next_pull": next_pull if next_pull in OUTCOME_LABELS else None,
    "next_pull_revealed": next_pull_revealed if next_pull in OUTCOME_LABELS else False,
    "guild_ids": normalized_guild_ids,
  }


def load_gamble_database(path="./databases/gambling.json"):
  """Load gamble data from MongoDB into memory cache."""
  global roulette_doubler
  try:
    documents = gamble_collection.find({})
    roulette_doubler = {}
    for doc in documents:
      user_id = int(doc['user_id'])
      player = _normalize_player_data(doc)
      player["money"] = get_user_balance(user_id)
      roulette_doubler[user_id] = player
    print(f"Loaded {len(roulette_doubler)} players from MongoDB")
  except Exception as e:
    print(f"Error loading gamble database: {e}")


def save_gamble_database(path="./databases/gambling.json"):
  """Save all player data to MongoDB."""
  try:
    for user_id, player_data in roulette_doubler.items():
      set_user_balance(user_id, player_data.get("money", 1))
      doc_payload = {k: v for k, v in player_data.items() if k not in ("money", "guild_id")}
      doc_payload['user_id'] = str(user_id)
      gamble_collection.update_one(
        {'user_id': str(user_id)},
        {'$set': doc_payload},
        upsert=True
      )
    print(f"Saved {len(roulette_doubler)} players to MongoDB")
  except Exception as e:
    print(f"Error saving gamble database: {e}")


def _resolve_pull_outcome(current_money, wager, pull):
  if pull == "LOSE_ALL":
    return 1, False, "BIG LOSS reset to $1"
  if pull == "TRIPLE_LOSS":
    return max(1, current_money - (3 * wager)), False, "CRITICAL LOSS (3x wager lost)"
  if pull == "DOUBLE_LOSS":
    return max(1, current_money - (2 * wager)), False, "HEAVY LOSS (2x wager lost)"
  if pull == "JACKPOT_10X":
    return current_money + (10 * wager), True, "LEGENDARY WIN (10x wager won)"
  if pull == "TRIPLE_WIN":
    return current_money + (3 * wager), True, "MAJOR WIN (3x wager won)"
  if pull == "DOUBLE_WIN":
    return current_money + (2 * wager), True, "BIG WIN (2x wager won)"
  if pull == "SINGLE_WIN":
    return current_money + wager, True, "WIN"
  return max(1, current_money - wager), False, "LOSS"


def _resolve_pool_outcome(current_money, wager):
  return _resolve_pull_outcome(current_money, wager, _next_pool_pull())


def _resolve_random_outcome(current_money, wager):
  return _resolve_pull_outcome(current_money, wager, _next_random_pull())


def resolve_gamble_outcome(current_money, wager):
  if mode == "pool":
    return _resolve_pool_outcome(current_money, wager)
  return _resolve_random_outcome(current_money, wager)


class _CooldownContext:
  def __init__(self, user):
    self.author = user


def _get_or_create_player(guild_id, user_id, user_name):
  """Get or create a player, fetching from MongoDB if not in cache."""
  uid = int(user_id)
  if uid not in roulette_doubler:
    # Try to load from MongoDB first
    try:
      db_player = gamble_collection.find_one({'user_id': str(user_id)})
      if db_player:
        player = _normalize_player_data(db_player)
      else:
        player = {
          "name": user_name,
          "win_streak": 0,
          "last_amount_change": 0,
          "last_multiplier": "N/A",
          "next_pull": None,
          "next_pull_revealed": False
        }
    except Exception as e:
      print(f"Error loading player from DB: {e}")
      player = {
        "name": user_name,
        "win_streak": 0,
        "last_amount_change": 0,
        "last_multiplier": "N/A",
        "next_pull": None,
        "next_pull_revealed": False
      }
    player["money"] = get_user_balance(user_id)
    roulette_doubler[uid] = player
  else:
    roulette_doubler[uid]["name"] = user_name
    roulette_doubler[uid]["money"] = get_user_balance(user_id)

  normalized_gid = str(guild_id)
  guild_ids = roulette_doubler[uid].get("guild_ids", [])
  if not isinstance(guild_ids, list):
    guild_ids = []
  if normalized_gid not in guild_ids:
    guild_ids.append(normalized_gid)
  roulette_doubler[uid]["guild_ids"] = guild_ids

  player = roulette_doubler[uid]
  if player["money"] < 1:
    player["money"] = 1
  if "win_streak" not in player or player["win_streak"] < 0:
    player["win_streak"] = 0
  if "last_amount_change" not in player:
    player["last_amount_change"] = 0
  if "last_multiplier" not in player:
    player["last_multiplier"] = "N/A"
  if "next_pull" not in player or player["next_pull"] not in OUTCOME_LABELS:
    player["next_pull"] = None
  if "next_pull_revealed" not in player:
    player["next_pull_revealed"] = False
  if "guild_ids" not in player or not isinstance(player["guild_ids"], list):
    player["guild_ids"] = [normalized_gid]
  if not player["next_pull"]:
    player["next_pull_revealed"] = False
  return player


def _build_gamble_embed(player):
  return build_gamble_embed(player, _pull_label)


def _create_gamble_view():
  return GambleView(
    amount_submit_handler=process_gamble_interaction,
    half_handler=_handle_gamble_half,
    all_handler=_handle_gamble_all,
    leaderboard_handler=_handle_leaderboard,
    pool_left_handler=_handle_pool_left,
    scry_handler=_handle_scry,
    reroll_handler=_handle_reroll,
    show_pool_left=(mode == "pool"),
  )


async def _send_or_refresh_panel_from_interaction(interaction, panel_message=None):
  player = _get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
  target_message = panel_message or getattr(interaction, "message", None)

  if target_message:
    await target_message.edit(
      content="Use the buttons below to keep gambling.",
      embed=_build_gamble_embed(player),
      view=_create_gamble_view()
    )
    return

  await interaction.followup.send(
    "Use the buttons below to keep gambling.",
    embed=_build_gamble_embed(player),
    view=_create_gamble_view()
  )


async def process_gamble_interaction(interaction, wager_input, panel_message=None):
  global roulette_doubler
  guild_id = str(interaction.guild_id)
  user_id = interaction.user.id
  user_name = interaction.user.display_name
  player = _get_or_create_player(guild_id, user_id, user_name)
  
  # Save to MongoDB after getting/creating player
  def _save_player_to_db():
    try:
      set_user_balance(user_id, player.get("money", 1))
      player_data = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
      player_data['user_id'] = str(user_id)
      gamble_collection.update_one(
        {'user_id': str(user_id)},
        {'$set': player_data, '$addToSet': {'guild_ids': guild_id}},
        upsert=True
      )
    except Exception as e:
      print(f"Error saving player {user_id}: {e}")

  wager_value = str(wager_input).strip().lower()
  if player.get("next_pull_revealed", False) and wager_value not in ("all", "half"):
    await interaction.response.send_message(
      "Custom wager amounts are disabled after Scry. Use Gamble Half, Gamble All, or Reroll.",
      ephemeral=True
    )
    return

  if wager_value == "all":
    wager = player["money"]
  elif wager_value == "half":
    wager = max(1, player["money"] // 2)
  else:
    try:
      wager = int(wager_value)
    except ValueError:
      await interaction.response.send_message(
        'Please indicate the amount you want to gamble using "gamble {amount to wager}".',
        ephemeral=True
      )
      return

  if wager <= 0:
    await interaction.response.send_message("Your wager must be greater than 0.", ephemeral=True)
    return

  if wager > player["money"]:
    await interaction.response.send_message(
      f"You only have {player['money']} to gamble.",
      ephemeral=True
    )
    return

  cooldown_ctx = _CooldownContext(interaction.user)
  bucket = message_cooldown.get_bucket(cooldown_ctx)
  retry_after = bucket.update_rate_limit()
  if retry_after:
    await interaction.response.send_message(
      f"STOP GAMBLING, you can gamble again after {round(retry_after, 2)} seconds",
      ephemeral=True
    )
    return

  previous_money = player["money"]
  reserved_pull = player.get("next_pull")
  if reserved_pull:
    updated_money, did_win, multiplier_text = _resolve_pull_outcome(player["money"], wager, reserved_pull)
    player["next_pull"] = None
    player["next_pull_revealed"] = False
  else:
    updated_money, did_win, multiplier_text = resolve_gamble_outcome(player["money"], wager)
  player["money"] = max(1, updated_money)
  player["last_amount_change"] = player["money"] - previous_money
  player["last_multiplier"] = multiplier_text
  if did_win:
    player["win_streak"] += 1
  else:
    player["win_streak"] = 0
  await interaction.response.defer()
  _save_player_to_db()  # Save to MongoDB
  await _send_or_refresh_panel_from_interaction(interaction, panel_message=panel_message)


async def _handle_gamble_half(interaction):
  await process_gamble_interaction(interaction, "half")


async def _handle_gamble_all(interaction):
  await process_gamble_interaction(interaction, "all")


async def _handle_leaderboard(interaction):
  await interaction.response.send_message(gamble_leaderboard(interaction.guild_id))


async def _handle_pool_left(interaction):
  await interaction.response.send_message(gamble_pool_breakdown(), ephemeral=True)


async def _handle_scry(interaction):
  guild_id = str(interaction.guild_id)
  player = _get_or_create_player(guild_id, interaction.user.id, interaction.user.display_name)
  if player["money"] < 15:
    await interaction.response.send_message("You need at least 15 balance to scry the next pull.", ephemeral=True)
    return
  if player.get("next_pull") and player.get("next_pull_revealed", False):
    await interaction.response.send_message(
      "Your next pull is already revealed in the panel. Gamble or reroll it.",
      ephemeral=True
    )
    return

  cost = _percent_cost(player["money"], 0.30)
  player["money"] = max(1, player["money"] - cost)
  player["last_amount_change"] = -cost
  player["last_multiplier"] = "PEEK FEE -30%"
  if not player.get("next_pull"):
    player["next_pull"] = _draw_next_pull()
  player["next_pull_revealed"] = True

  # Save to MongoDB
  try:
    set_user_balance(interaction.user.id, player.get("money", 1))
    player_data = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
    player_data['user_id'] = str(interaction.user.id)
    gamble_collection.update_one(
      {'user_id': str(interaction.user.id)},
      {'$set': player_data, '$addToSet': {'guild_ids': guild_id}},
      upsert=True
    )
  except Exception as e:
    print(f"Error saving player: {e}")

  await interaction.response.defer()
  await _send_or_refresh_panel_from_interaction(interaction)


async def _handle_reroll(interaction):
  guild_id = str(interaction.guild_id)
  player = _get_or_create_player(guild_id, interaction.user.id, interaction.user.display_name)
  if player["money"] < 10:
    await interaction.response.send_message("You need at least 10 balance to reroll your next pull.", ephemeral=True)
    return

  cost = _percent_cost(player["money"], 0.15)
  if not player.get("next_pull"):
    player["next_pull"] = _draw_next_pull()
  player["money"] = max(1, player["money"] - cost)
  player["last_amount_change"] = -cost
  player["last_multiplier"] = "REROLL FEE -15%"
  player["next_pull"] = _draw_next_pull()
  player["next_pull_revealed"] = False

  # Save to MongoDB
  try:
    set_user_balance(interaction.user.id, player.get("money", 1))
    player_data = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
    player_data['user_id'] = str(interaction.user.id)
    gamble_collection.update_one(
      {'user_id': str(interaction.user.id)},
      {'$set': player_data, '$addToSet': {'guild_ids': guild_id}},
      upsert=True
    )
  except Exception as e:
    print(f"Error saving player: {e}")

  await interaction.response.defer()
  await _send_or_refresh_panel_from_interaction(interaction)


async def send_gamble_panel(msg):
  if msg.guild is None:
    await msg.reply("Gamble only works in a server.")
    return
  player = _get_or_create_player(msg.guild.id if msg.guild else None, msg.author.id, msg.author.display_name)
  panel_text = "Welcome to the Catgpt Gamble Game! Use the buttons below to start gambling." if player["money"] == 1 else "Welcome back to the Catgpt Gamble Game! Use the buttons below to keep gambling."
  await msg.reply(panel_text, embed=_build_gamble_embed(player), view=_create_gamble_view())


async def roulette(msg):
  await send_gamble_panel(msg)


def gamble_leaderboard(guild_id, limit=10):
  guild_players = get_gamble_leaderboard(guild_id, limit)

  if not guild_players:
    return "No gambling records yet."

  lines = ["🏆 Gamble Leaderboard"]
  for rank, player_data in enumerate(guild_players, start=1):
    lines.append(f"{rank}. {player_data['name']} - {player_data['money']}")

  return "\n".join(lines)


def gamble_balance(guild_id, user_id):
  return get_user_balance(guild_id, user_id)


def gamble_pool_pulls_left():
  if mode != "pool":
    return "Pool mode is off."
  return f"{len(pool_pulls)} pulls left in the current pool."


def gamble_pool_breakdown():
  if mode != "pool":
    return "Pool mode is off."

  if not pool_pulls:
    current_pulls = _build_pool_pulls()
  else:
    current_pulls = list(pool_pulls)

  counts = Counter(current_pulls)
  order = [
    ("JACKPOT_10X", "10x Jackpot"),
    ("TRIPLE_WIN", "Triple Win"),
    ("DOUBLE_WIN", "Double Win"),
    ("LOSE_ALL", "Lose All"),
    ("TRIPLE_LOSS", "Triple Loss"),
    ("DOUBLE_LOSS", "Double Loss"),
    ("SINGLE_WIN", "Single Win"),
    ("SINGLE_LOSS", "Single Loss"),
  ]

  lines = [f"Pool mode is on. {len(current_pulls)} pulls left:"]
  for key, label in order:
    lines.append(f"{label}: {counts.get(key, 0)}")
  return "\n".join(lines)
