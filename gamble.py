import random
import math
import time
from gamble_constants import (
  ABILITY_LIMITS,
  FOUNDATION_BASE_BALANCE_BY_LEVEL,
  FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL,
  HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL,
  INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL,
  PASSION_GAMBLE_COOLDOWN_SECONDS_BY_LEVEL,
  REROLL_COST_PERCENT,
  SCRY_COST_BY_SAGE,
  SPECIAL_EVENT_BUCKET_PERCENT,
  SPECIAL_EVENT_WEIGHTS,
)
from gamble_ui import (
  build_gamble_embed,
  GambleView,
  GambleMenuView,
  build_gamble_menu_embed,
  AscendConfirmView,
  build_ascension_abilities_embed,
  AscensionAbilitiesView,
)
from db import gamble_collection, get_user_balance, set_user_balance, get_gamble_leaderboard

roulette_doubler = {}  # In-memory cache of player data
last_gamble_at = {}

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

ASCEND_COST = 1_000_000

def _get_gamble_cooldown_seconds(player):
  abilities = _get_effective_abilities(player)
  passion_level = int(abilities.get("passion", 0) or 0)
  return PASSION_GAMBLE_COOLDOWN_SECONDS_BY_LEVEL.get(passion_level, PASSION_GAMBLE_COOLDOWN_SECONDS_BY_LEVEL[0])


def _get_ascend_stars(current_money):
  return max(0, int(math.log10(max(1, int(current_money))) - 5))


def _get_scry_cost_percent(player):
  abilities = _get_effective_abilities(player)
  sage_level = int(abilities.get("sage", 0) or 0)
  return SCRY_COST_BY_SAGE.get(sage_level, 20.0)


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


def _next_random_pull_for_player(player):
  abilities = _get_effective_abilities(player)
  fickle_level = int(abilities.get("fickle", 0) or 0)
  influence_level = int(abilities.get("influence", 0) or 0)
  heavy_level = int(abilities.get("heavy_die", 0) or 0)

  bonus_event = FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL.get(fickle_level, FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL[2] if fickle_level >= 2 else 0.0)

  # Total "event" probability is the special outcomes bucket.
  base_event = SPECIAL_EVENT_BUCKET_PERCENT
  p_event = max(0.0, min(100.0, base_event + bonus_event))

  # Influence biases event outcomes toward good results without changing p_event.
  pos_ratio = INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL.get(
    influence_level,
    INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL[3] if influence_level >= 3 else INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL[0],
  )

  # Heavy Die changes the single win/loss ratio.
  single_win_ratio = HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL.get(
    heavy_level,
    HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL[3] if heavy_level >= 3 else HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL[0],
  )

  # Base per-event distribution (balanced 7.5% good / 7.5% bad)
  base_pos = {key: SPECIAL_EVENT_WEIGHTS[key] for key in ("JACKPOT_10X", "TRIPLE_WIN", "DOUBLE_WIN")}
  base_neg = {key: SPECIAL_EVENT_WEIGHTS[key] for key in ("LOSE_ALL", "TRIPLE_LOSS", "DOUBLE_LOSS")}
  base_pos_total = sum(base_pos.values())
  base_neg_total = sum(base_neg.values())

  p_event_pos = p_event * pos_ratio
  p_event_neg = p_event - p_event_pos

  thresholds = []
  cumulative = 0.0

  # Negative events
  for key, weight in base_neg.items():
    cumulative += (p_event_neg * (weight / base_neg_total)) if base_neg_total > 0 else 0.0
    thresholds.append((cumulative, key))

  # Positive events
  for key, weight in base_pos.items():
    cumulative += (p_event_pos * (weight / base_pos_total)) if base_pos_total > 0 else 0.0
    thresholds.append((cumulative, key))

  # Singles (non-events)
  remaining = max(0.0, 100.0 - p_event)
  cumulative += remaining * single_win_ratio
  thresholds.append((cumulative, "SINGLE_WIN"))
  cumulative += remaining * (1.0 - single_win_ratio)
  thresholds.append((cumulative, "SINGLE_LOSS"))

  roll = random.random() * 100.0
  for cutoff, key in thresholds:
    if roll < cutoff:
      return key
  return "SINGLE_LOSS"


def _draw_next_pull(player=None):
  if player is not None:
    return _next_random_pull_for_player(player)
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
    gambler_stars = player_data.get("gambler_stars", 0)
    ascension_abilities = player_data.get("ascension_abilities", {})
  else:
    name = "Unknown"
    win_streak = 0
    last_amount_change = 0
    last_multiplier = "N/A"
    next_pull = None
    next_pull_revealed = False
    guild_ids = []
    gambler_stars = 0
    ascension_abilities = {}

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

  try:
    gambler_stars = int(gambler_stars)
  except (TypeError, ValueError):
    gambler_stars = 0

  if gambler_stars < 0:
    gambler_stars = 0

  if not isinstance(guild_ids, list):
    guild_ids = []

  if not isinstance(ascension_abilities, dict):
    ascension_abilities = {}

  normalized_abilities = {
    "foundation": ascension_abilities.get("foundation", 0),
    "fickle": ascension_abilities.get("fickle", 0),
    "influence": ascension_abilities.get("influence", 0),
    "heavy_die": ascension_abilities.get("heavy_die", 0),
    "sage": ascension_abilities.get("sage", 0),
    "passion": ascension_abilities.get("passion", 0),
    "unbounded": bool(ascension_abilities.get("unbounded", False)),
    "blessed": bool(ascension_abilities.get("blessed", False)),
    "greed": bool(ascension_abilities.get("greed", False)),
  }
  for key, cap in ABILITY_LIMITS.items():
    try:
      normalized_abilities[key] = int(normalized_abilities.get(key, 0))
    except (TypeError, ValueError):
      normalized_abilities[key] = 0
    normalized_abilities[key] = max(0, min(cap, normalized_abilities[key]))

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
    "gambler_stars": gambler_stars,
    "ascension_abilities": normalized_abilities,
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


def _resolve_pull_outcome(current_money, wager, pull, *, min_balance=1, greed_active=False):
  floor_amount = max(1, int(min_balance))

  # Greed consequence: any negative event resets you.
  if greed_active and pull in ("LOSE_ALL", "TRIPLE_LOSS", "DOUBLE_LOSS"):
    return floor_amount, False, f"GREED CURSE reset to ${floor_amount}"

  if pull == "LOSE_ALL":
    return floor_amount, False, f"BIG LOSS reset to ${floor_amount}"
  if pull == "TRIPLE_LOSS":
    return max(floor_amount, current_money - (3 * wager)), False, "CRITICAL LOSS (3x wager lost)"
  if pull == "DOUBLE_LOSS":
    return max(floor_amount, current_money - (2 * wager)), False, "HEAVY LOSS (2x wager lost)"
  if pull == "JACKPOT_10X":
    return current_money + (10 * wager), True, "LEGENDARY WIN (10x wager won)"
  if pull == "TRIPLE_WIN":
    return current_money + (3 * wager), True, "MAJOR WIN (3x wager won)"
  if pull == "DOUBLE_WIN":
    return current_money + (2 * wager), True, "BIG WIN (2x wager won)"
  if pull == "SINGLE_WIN":
    return current_money + wager, True, "WIN"
  return max(floor_amount, current_money - wager), False, "LOSS"


def resolve_gamble_outcome(player, wager):
  min_balance = _get_base_balance(player)
  greed_active = bool(_get_effective_abilities(player).get("greed", False))
  pull = _next_random_pull_for_player(player)
  return _resolve_pull_outcome(player["money"], wager, pull, min_balance=min_balance, greed_active=greed_active)


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
          "next_pull_revealed": False,
          "gambler_stars": 0,
          "ascension_abilities": {},
        }
    except Exception as e:
      print(f"Error loading player from DB: {e}")
      player = {
        "name": user_name,
        "win_streak": 0,
        "last_amount_change": 0,
        "last_multiplier": "N/A",
        "next_pull": None,
        "next_pull_revealed": False,
        "gambler_stars": 0,
        "ascension_abilities": {},
      }

    # If the user has no balance record yet, start at their current foundation base.
    base_default = 1
    try:
      base_default = max(1, int(_get_base_balance(player)))
    except Exception:
      base_default = 1
    player["money"] = get_user_balance(user_id, default_balance=base_default)
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
  if "gambler_stars" not in player:
    player["gambler_stars"] = 0
  if not isinstance(player["gambler_stars"], int) or player["gambler_stars"] < 0:
    try:
      player["gambler_stars"] = max(0, int(player["gambler_stars"]))
    except (TypeError, ValueError):
      player["gambler_stars"] = 0
  if "ascension_abilities" not in player or not isinstance(player["ascension_abilities"], dict):
    player["ascension_abilities"] = _normalize_player_data({"ascension_abilities": {}}).get("ascension_abilities", {})
  else:
    # normalize bounds/types in-place
    player["ascension_abilities"] = _normalize_player_data({"ascension_abilities": player["ascension_abilities"]}).get("ascension_abilities", {})
  if "guild_ids" not in player or not isinstance(player["guild_ids"], list):
    player["guild_ids"] = [normalized_gid]
  if not player["next_pull"]:
    player["next_pull_revealed"] = False
  return player


def _get_effective_abilities(player):
  abilities = player.get("ascension_abilities")
  if not isinstance(abilities, dict):
    abilities = {}
  abilities = _normalize_player_data({"ascension_abilities": abilities}).get("ascension_abilities", {})

  if bool(abilities.get("greed", False)):
    return {
      "foundation": 1,
      "fickle": 1,
      "influence": 1,
      "heavy_die": 1,
      "sage": 1,
      "passion": 1,
      "unbounded": True,
      "blessed": True,
      "greed": True,
    }
  return abilities


def _get_base_balance(player):
  abilities = _get_effective_abilities(player)
  foundation = int(abilities.get("foundation", 0) or 0)
  return int(FOUNDATION_BASE_BALANCE_BY_LEVEL.get(foundation, FOUNDATION_BASE_BALANCE_BY_LEVEL[0]))


def _get_prestige_start_balance(player):
  base = _get_base_balance(player)
  abilities = _get_effective_abilities(player)
  if bool(abilities.get("blessed", False)):
    return max(base, 1000)
  return base


def _save_player_to_db(user_id, guild_id, player):
  try:
    set_user_balance(user_id, player.get("money", 1))
    player_data = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
    player_data["user_id"] = str(user_id)
    gamble_collection.update_one(
      {"user_id": str(user_id)},
      {"$set": player_data, "$addToSet": {"guild_ids": str(guild_id)}},
      upsert=True
    )
  except Exception as e:
    print(f"Error saving player {user_id}: {e}")


def _build_gamble_embed(player):
  return build_gamble_embed(player, _pull_label)


def _create_gamble_view(player):
  view = GambleView(
    player,
    amount_submit_handler=process_gamble_interaction,
    half_handler=_handle_gamble_half,
    all_handler=_handle_gamble_all,
    leaderboard_handler=_handle_leaderboard,
    scry_handler=_handle_scry,
    reroll_handler=_handle_reroll,
    ascend_handler=_handle_ascend,
    ascension_abilities_handler=_handle_ascension_abilities,
  )
  # wire the menu handler to open the Gamble Menu view
  view.menu_handler = _open_gamble_menu
  return view


async def _handle_ascension_abilities(interaction, panel_message=None):
  if interaction.guild is None:
    await interaction.response.send_message("Ascension abilities only work in a server.", ephemeral=True)
    return

  player = _get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
  abilities = _get_effective_abilities(player)
  has_any_abilities = any(
    [
      int(abilities.get("foundation", 0) or 0) > 0,
      int(abilities.get("fickle", 0) or 0) > 0,
      int(abilities.get("influence", 0) or 0) > 0,
      int(abilities.get("heavy_die", 0) or 0) > 0,
      int(abilities.get("sage", 0) or 0) > 0,
      int(abilities.get("passion", 0) or 0) > 0,
      bool(abilities.get("unbounded", False)),
      bool(abilities.get("blessed", False)),
      bool(abilities.get("greed", False)),
    ]
  )
  if int(player.get("gambler_stars", 0) or 0) <= 0 and not has_any_abilities:
    await interaction.response.send_message("You must ascend once to see the abilities page.", ephemeral=True)
    return
  await interaction.response.send_message(
    embed=build_ascension_abilities_embed(player),
    view=AscensionAbilitiesView(player, purchase_handler=_purchase_ascension_ability, panel_message=panel_message),
    ephemeral=True,
  )


async def _purchase_ascension_ability(interaction, action=None, panel_message=None):
  if interaction.guild is None:
    await interaction.response.send_message("Ascension abilities only work in a server.", ephemeral=True)
    return

  if not isinstance(action, dict):
    await interaction.response.send_message("Invalid ability action.", ephemeral=True)
    return

  player = _get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
  abilities = player.get("ascension_abilities")
  if not isinstance(abilities, dict):
    abilities = {}
  abilities = _normalize_player_data({"ascension_abilities": abilities}).get("ascension_abilities", {})

  stars = int(player.get("gambler_stars", 0) or 0)

  key = str(action.get("key", "")).strip()
  action_type = action.get("type")

  if bool(abilities.get("greed", False)) and key != "greed":
    await interaction.response.send_message("Greed is active. Remove it before buying other abilities.", ephemeral=True)
    return

  changed = False
  previous_money = int(player.get("money", 1) or 1)
  if action_type == "advance":
    if key in ABILITY_LIMITS:
      cap = ABILITY_LIMITS[key]
      current = int(abilities.get(key, 0) or 0)
      if current >= cap:
        await interaction.response.send_message("That ability is already maxed.", ephemeral=True)
        return
      abilities[key] = current + 1
      changed = True
    elif key in ("unbounded", "blessed"):
      if bool(abilities.get(key, False)):
        await interaction.response.send_message("That ability is already owned.", ephemeral=True)
        return
      abilities[key] = True
      changed = True
    else:
      await interaction.response.send_message("Invalid ability.", ephemeral=True)
      return

  elif action_type == "toggle":
    if key != "greed":
      await interaction.response.send_message("Invalid toggle ability.", ephemeral=True)
      return
    if stars < 1:
      await interaction.response.send_message("You need at least 1 Star.", ephemeral=True)
      return
    if bool(abilities.get("greed", False)):
      abilities["greed"] = False
    else:
      abilities["greed"] = True
    changed = True

  else:
    await interaction.response.send_message("Invalid ability action type.", ephemeral=True)
    return

  if not changed:
    await interaction.response.send_message("No change applied.", ephemeral=True)
    return

  if action_type == "toggle" and key == "greed":
    player["gambler_stars"] = max(0, stars - 1)
  else:
    player["gambler_stars"] = max(0, stars - 1)
  player["ascension_abilities"] = abilities

  # Foundation: immediately lift current balance to the new base.
  if action_type == "advance" and key == "foundation":
    temp_player = dict(player)
    temp_player["ascension_abilities"] = abilities
    new_base = _get_base_balance(temp_player)
    try:
      new_base = int(new_base)
    except (TypeError, ValueError):
      new_base = 1
    new_base = max(1, new_base)

    current_money = int(player.get("money", 1) or 1)
    player["money"] = max(current_money, new_base)

    if int(player["money"]) != previous_money:
      player["last_amount_change"] = int(player["money"]) - previous_money
      player["last_multiplier"] = f"FOUNDATION set base to ${new_base:,}"

  _save_player_to_db(interaction.user.id, str(interaction.guild_id), player)

  await interaction.response.edit_message(
    embed=build_ascension_abilities_embed(player),
    view=AscensionAbilitiesView(player, purchase_handler=_purchase_ascension_ability, panel_message=panel_message),
    content="Purchased.",
  )

  await _send_or_refresh_panel_from_interaction(interaction, panel_message=panel_message)


async def _send_or_refresh_panel_from_interaction(interaction, panel_message=None):
  player = _get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
  target_message = panel_message or getattr(interaction, "message", None)
  # Try to acknowledge the interaction first to avoid reusing the same interaction
  if target_message:
    try:
      await interaction.response.edit_message(
        content="Use the buttons below to keep gambling.",
        embed=_build_gamble_embed(player),
        view=_create_gamble_view(player)
      )
      return
    except Exception:
      # If response has already been used, fall back to editing the message object
      await target_message.edit(
        content="Use the buttons below to keep gambling.",
        embed=_build_gamble_embed(player),
        view=_create_gamble_view(player)
      )
      return

  try:
    await interaction.response.send_message(
      "Use the buttons below to keep gambling.",
      embed=_build_gamble_embed(player),
      view=_create_gamble_view(player)
    )
  except Exception:
    await interaction.followup.send(
      "Use the buttons below to keep gambling.",
      embed=_build_gamble_embed(player),
      view=_create_gamble_view(player)
    )


async def _open_gamble_menu(interaction, panel_message=None):
  # Show the Gamble Menu (Leaderboard / Ascend / Abilities)
  player = _get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
  target_message = panel_message or getattr(interaction, "message", None)

  menu_view = GambleMenuView(
    player,
    leaderboard_handler=_handle_leaderboard,
    ascend_handler=_handle_ascend,
    ascension_abilities_handler=_handle_ascension_abilities,
    gamble_handler=_send_or_refresh_panel_from_interaction,
    panel_message=panel_message,
  )

  if target_message:
    try:
      await interaction.response.edit_message(
        content="Gamble Menu",
        embed=build_gamble_menu_embed(player),
        view=menu_view,
      )
      return
    except Exception:
      # If the interaction was already responded to, fall back to editing the message object
      await target_message.edit(
        content="Gamble Menu",
        embed=build_gamble_menu_embed(player),
        view=menu_view,
      )
      return

  try:
    await interaction.response.send_message(
      "Gamble Menu",
      embed=build_gamble_menu_embed(player),
      view=menu_view,
    )
  except Exception:
    await interaction.followup.send(
      "Gamble Menu",
      embed=build_gamble_menu_embed(player),
      view=menu_view,
    )


async def process_gamble_interaction(interaction, wager_input, panel_message=None):
  global roulette_doubler
  guild_id = str(interaction.guild_id)
  user_id = interaction.user.id
  user_name = interaction.user.display_name
  player = _get_or_create_player(guild_id, user_id, user_name)

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

  now = time.monotonic()
  cooldown_seconds = _get_gamble_cooldown_seconds(player)
  last_used_at = last_gamble_at.get(user_id)
  if last_used_at is not None:
    retry_after = cooldown_seconds - (now - last_used_at)
  else:
    retry_after = 0
  if retry_after and retry_after > 0:
    await interaction.response.send_message(
      f"STOP GAMBLING, you can gamble again after {round(retry_after, 2)} seconds",
      ephemeral=True
    )
    return
  last_gamble_at[user_id] = now

  previous_money = player["money"]
  reserved_pull = player.get("next_pull")
  if reserved_pull:
    updated_money, did_win, multiplier_text = _resolve_pull_outcome(
      player["money"],
      wager,
      reserved_pull,
      min_balance=_get_base_balance(player),
      greed_active=bool(_get_effective_abilities(player).get("greed", False)),
    )
    player["next_pull"] = None
    player["next_pull_revealed"] = False
  else:
    updated_money, did_win, multiplier_text = resolve_gamble_outcome(player, wager)
  player["money"] = max(1, updated_money)
  player["last_amount_change"] = player["money"] - previous_money
  player["last_multiplier"] = multiplier_text
  if did_win:
    player["win_streak"] += 1
  else:
    player["win_streak"] = 0
  await interaction.response.defer()
  _save_player_to_db(user_id, guild_id, player)  # Save to MongoDB
  await _send_or_refresh_panel_from_interaction(interaction, panel_message=panel_message)


async def _handle_ascend(interaction, panel_message=None):
  if interaction.guild is None:
    await interaction.response.send_message("Ascend only works in a server.", ephemeral=True)
    return

  confirm_text = (
    f"Ascension requires a minimum of ${ASCEND_COST:,} and grants Stars based on your money.\n You will lose all your money. Are you sure?"
  )
  await interaction.response.send_message(
    confirm_text,
    view=AscendConfirmView(confirm_handler=_confirm_ascend, panel_message=panel_message),
    ephemeral=True
  )


async def _confirm_ascend(interaction, panel_message=None):
  guild_id = str(interaction.guild_id)
  user_id = interaction.user.id
  player = _get_or_create_player(guild_id, user_id, interaction.user.display_name)

  current_money = int(player.get("money", 1))
  if current_money < ASCEND_COST:
    await interaction.response.edit_message(
      content=f"You need at least ${ASCEND_COST:,} to Ascend.",
      view=None
    )
    return

  stars_awarded = _get_ascend_stars(current_money)
  player["gambler_stars"] = int(player.get("gambler_stars", 0)) + stars_awarded
  # "Prestige" reset: after paying the cost, start the new prestige at your base/blesed balance.
  prestige_start = _get_prestige_start_balance(player)
  player["money"] = max(1, int(prestige_start))
  player["win_streak"] = 0
  player["next_pull"] = None
  player["next_pull_revealed"] = False
  player["last_amount_change"] = int(player["money"]) - int(current_money)
  player["last_multiplier"] = f"ASCENDED (+{stars_awarded} star{'s' if stars_awarded != 1 else ''}, start ${int(prestige_start):,})"

  _save_player_to_db(user_id, guild_id, player)

  await interaction.response.edit_message(
    content=f"Ascension complete. (+{stars_awarded} Star{'s' if stars_awarded != 1 else ''})",
    view=None
  )

  # Public server announcement.
  try:
    if interaction.guild is not None and interaction.channel is not None:
      await interaction.channel.send(f"{interaction.user.display_name} has ascended")
  except Exception as e:
    print(f"Error sending ascension announcement for {user_id}: {e}")

  await _send_or_refresh_panel_from_interaction(interaction, panel_message=panel_message)


async def _handle_gamble_half(interaction):
  await process_gamble_interaction(interaction, "half")


async def _handle_gamble_all(interaction):
  await process_gamble_interaction(interaction, "all")


async def _handle_leaderboard(interaction):
  await interaction.response.send_message(gamble_leaderboard(interaction.guild_id))


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

  cost_percent = _get_scry_cost_percent(player)
  cost = _percent_cost(player["money"], cost_percent / 100.0)
  player["money"] = max(1, player["money"] - cost)
  player["last_amount_change"] = -cost
  player["last_multiplier"] = f"PEEK FEE -{int(cost_percent) if cost_percent.is_integer() else cost_percent}%"
  if not player.get("next_pull"):
    player["next_pull"] = _draw_next_pull(player)
  player["next_pull_revealed"] = True

  _save_player_to_db(interaction.user.id, guild_id, player)

  await interaction.response.defer()
  await _send_or_refresh_panel_from_interaction(interaction)


async def _handle_reroll(interaction):
  guild_id = str(interaction.guild_id)
  player = _get_or_create_player(guild_id, interaction.user.id, interaction.user.display_name)
  if player["money"] < 10:
    await interaction.response.send_message("You need at least 10 balance to reroll your next pull.", ephemeral=True)
    return

  abilities = _get_effective_abilities(player)
  ratio = REROLL_COST_PERCENT
  if bool(abilities.get("unbounded", False)):
    ratio = ratio / 2.0
  cost = _percent_cost(player["money"], ratio)
  if not player.get("next_pull"):
    player["next_pull"] = _draw_next_pull(player)
  player["money"] = max(1, player["money"] - cost)
  player["last_amount_change"] = -cost
  player["last_multiplier"] = f"REROLL FEE -{bool(abilities.get("unbounded", False)) and "7.5%" or "15%"}"
  player["next_pull"] = _draw_next_pull(player)
  player["next_pull_revealed"] = False

  _save_player_to_db(interaction.user.id, guild_id, player)

  await interaction.response.defer()
  await _send_or_refresh_panel_from_interaction(interaction)


async def send_gamble_panel(msg):
  if msg.guild is None:
    await msg.reply("Gamble only works in a server.")
    return
  player = _get_or_create_player(msg.guild.id if msg.guild else None, msg.author.id, msg.author.display_name)
  panel_text = "Welcome to the Catgpt Gamble Game! Use the buttons below to start gambling." if player["money"] == 1 else "Welcome back to the Catgpt Gamble Game! Use the buttons below to keep gambling."
  await msg.reply(panel_text, embed=_build_gamble_embed(player), view=_create_gamble_view(player))


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
