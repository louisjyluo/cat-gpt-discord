"""
gamble_state.py
───────────────
Player data layer — in-memory cache backed by MongoDB.

Two module-level dicts:
  _players        : int → player dict   (keyed by user_id)
  _last_gamble_at : int → float         (monotonic timestamp per user)

No game logic lives here. All normalization/defaults are in gamble_logic.
"""
from __future__ import annotations

from db import gamble_collection, get_user_balance, set_user_balance
from .gamble_logic import normalize_player, get_base_balance

_players: dict[int, dict] = {}
_last_gamble_at: dict[int, float] = {}


def get_or_create_player(guild_id, user_id, user_name: str) -> dict:
    uid = int(user_id)
    if uid not in _players:
        try:
            raw = gamble_collection.find_one({"user_id": str(user_id)})
        except Exception as e:
            print(f"DB read error for {user_id}: {e}")
            raw = None
        player = normalize_player(raw or {})
        player["name"] = user_name
        base = max(1, get_base_balance(player))
        player["money"] = get_user_balance(user_id, default_balance=base)
        _players[uid] = player
    else:
        _players[uid]["name"] = user_name
        _players[uid]["money"] = get_user_balance(user_id)

    p = _players[uid]
    gid = str(guild_id)
    guild_ids = p.get("guild_ids", [])
    if not isinstance(guild_ids, list):
        guild_ids = []
    if gid not in guild_ids:
        guild_ids.append(gid)
    p["guild_ids"] = guild_ids
    if p.get("money", 1) < 1:
        p["money"] = 1
    return p


def save_player(user_id, guild_id: str, player: dict) -> None:
    uid = int(user_id)
    _players[uid] = player
    try:
        set_user_balance(user_id, player.get("money", 1))
        payload = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
        payload["user_id"] = str(user_id)
        gamble_collection.update_one(
            {"user_id": str(user_id)},
            {"$set": payload, "$addToSet": {"guild_ids": str(guild_id)}},
            upsert=True,
        )
    except Exception as e:
        print(f"DB write error for {user_id}: {e}")


def get_last_gamble_at(user_id) -> float | None:
    return _last_gamble_at.get(int(user_id))


def set_last_gamble_at(user_id, ts: float) -> None:
    _last_gamble_at[int(user_id)] = ts


def load_gamble_database(path: str = "./databases/gambling.json") -> None:
    """Populate in-memory cache from MongoDB on startup."""
    global _players
    try:
        docs = gamble_collection.find({})
        _players = {}
        for doc in docs:
            uid = int(doc["user_id"])
            player = normalize_player(doc)
            player["money"] = get_user_balance(uid)
            _players[uid] = player
        print(f"Loaded {len(_players)} players from MongoDB")
    except Exception as e:
        print(f"Error loading gamble database: {e}")


def save_gamble_database(path: str = "./databases/gambling.json") -> None:
    """Flush all in-memory players back to MongoDB on shutdown."""
    try:
        for uid, player in _players.items():
            set_user_balance(uid, player.get("money", 1))
            payload = {k: v for k, v in player.items() if k not in ("money", "guild_ids")}
            payload["user_id"] = str(uid)
            gamble_collection.update_one(
                {"user_id": str(uid)},
                {"$set": payload},
                upsert=True,
            )
        print(f"Saved {len(_players)} players to MongoDB")
    except Exception as e:
        print(f"Error saving gamble database: {e}")
