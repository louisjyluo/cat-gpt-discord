"""
gamble_logic.py
───────────────
Pure game logic — no I/O, no Discord, no global state.

Every function takes plain dicts and returns plain values or NEW dicts.
Input dicts are NEVER mutated; callers receive a shallow copy with changes applied.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from .gamble_constants import (
    ABILITY_LIMITS,
    ASCEND_COST,
    FOUNDATION_BASE_BALANCE_BY_LEVEL,
    FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL,
    HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL,
    INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL,
    OUTCOME_LABELS,
    PASSION_GAMBLE_COOLDOWN_SECONDS_BY_LEVEL,
    REROLL_COST_PERCENT,
    SCRY_COST_BY_SAGE,
    SPECIAL_EVENT_BUCKET_PERCENT,
    SPECIAL_EVENT_WEIGHTS,
)


# ─── Data normalization ────────────────────────────────────────────────────────

def normalize_player(raw: Optional[dict]) -> dict:
    """
    Coerce a raw MongoDB document (or None/partial dict) into a valid player dict.
    Always safe to call; returns sensible defaults for every missing field.
    """
    if not isinstance(raw, dict):
        raw = {}

    def _int(val, *, floor: int = 0) -> int:
        try:
            return max(floor, int(val or 0))
        except (TypeError, ValueError):
            return floor

    # ── Abilities ──────────────────────────────────────────────────────────────
    raw_ab = raw.get("ascension_abilities", {})
    if not isinstance(raw_ab, dict):
        raw_ab = {}
    abilities: dict = {}
    for key, cap in ABILITY_LIMITS.items():
        abilities[key] = max(0, min(cap, _int(raw_ab.get(key))))
    abilities["unbounded"] = bool(raw_ab.get("unbounded", False))
    abilities["blessed"] = bool(raw_ab.get("blessed", False))

    next_pull = raw.get("next_pull")
    if next_pull not in OUTCOME_LABELS:
        next_pull = None

    _tm_raw = raw.get("true_money")
    try:
        _true_money = int(_tm_raw) if _tm_raw is not None else 0
    except (TypeError, ValueError):
        _true_money = 0

    return {
        "name": str(raw.get("name", "Unknown")),
        "win_streak": _int(raw.get("win_streak"), floor=0),
        "last_amount_change": _int(raw.get("last_amount_change")),
        "last_multiplier": str(raw.get("last_multiplier", "N/A")),
        "next_pull": next_pull,
        "next_pull_revealed": bool(raw.get("next_pull_revealed", False)) and next_pull is not None,
        "gambler_stars": _int(raw.get("gambler_stars"), floor=0),
        "ascension_abilities": abilities,
        "true_mode": bool(raw.get("true_mode", False)),
        "true_winrate_wins": _int(raw.get("true_winrate_wins"), floor=0),
        "true_winrate_total": _int(raw.get("true_winrate_total"), floor=0),
        "true_money": _true_money,
        "guild_ids": [],  # managed by the state layer
    }


# ─── Read-only accessors ──────────────────────────────────────────────────────

def get_effective_abilities(player: dict) -> dict:
    """
    Return the player's ability levels after applying sin overrides.
    Envy grants all tier-1 abilities at level 1; Greed nullifies Heavy Die.
    """
    raw = player.get("ascension_abilities", {})
    if not isinstance(raw, dict):
        raw = {}
    ab: dict = {}
    for key, cap in ABILITY_LIMITS.items():
        try:
            ab[key] = max(0, min(cap, int(raw.get(key, 0) or 0)))
        except (TypeError, ValueError):
            ab[key] = 0
    ab["unbounded"] = bool(raw.get("unbounded", False))
    ab["blessed"] = bool(raw.get("blessed", False))
    return ab


def get_base_balance(player: dict) -> int:
    foundation = int(get_effective_abilities(player).get("foundation", 0) or 0)
    return int(FOUNDATION_BASE_BALANCE_BY_LEVEL.get(foundation, 1))


def get_prestige_start_balance(player: dict) -> int:
    base = get_base_balance(player)
    if bool(get_effective_abilities(player).get("blessed", False)):
        return max(base, 1000)
    return base


def get_gamble_cooldown(player: dict) -> float:
    passion = int(get_effective_abilities(player).get("passion", 0) or 0)
    return float(PASSION_GAMBLE_COOLDOWN_SECONDS_BY_LEVEL.get(passion, 4.0))


def get_scry_cost_percent(player: dict) -> float:
    sage = int(get_effective_abilities(player).get("sage", 0) or 0)
    return float(SCRY_COST_BY_SAGE.get(sage, 20.0))


def get_reroll_cost_ratio(player: dict) -> float:
    ratio = REROLL_COST_PERCENT / 100.0
    if bool(get_effective_abilities(player).get("unbounded", False)):
        ratio /= 2.0
    return ratio


def get_win_probability_percent(player: dict) -> float:
    ab = get_effective_abilities(player)
    fickle = int(ab.get("fickle", 0) or 0)
    influence = int(ab.get("influence", 0) or 0)
    heavy = int(ab.get("heavy_die", 0) or 0)

    bonus = FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL.get(fickle, 0.0)
    p_event = max(0.0, min(100.0, SPECIAL_EVENT_BUCKET_PERCENT + bonus))
    pos_ratio = INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL.get(influence, 0.50)
    p_event_pos = p_event * pos_ratio
    remaining = max(0.0, 100.0 - p_event)
    rate = HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL.get(heavy, 0.50)
    return p_event_pos + remaining * rate


def get_ascend_stars(money: int) -> int:
    return max(0, int(math.log10(max(1, int(money))) - 4))


def pull_label(pull: Optional[str]) -> str:
    return OUTCOME_LABELS.get(pull, "Unknown") if pull else "Hidden"


# ─── Random outcome generation ────────────────────────────────────────────────

def draw_pull(player: dict) -> str:
    """Draw a random pull outcome, weighted by the player's active abilities."""
    ab = get_effective_abilities(player)
    fickle = int(ab.get("fickle", 0) or 0)
    influence = int(ab.get("influence", 0) or 0)
    heavy = int(ab.get("heavy_die", 0) or 0)

    bonus = FICKLE_EVENT_BONUS_PERCENT_BY_LEVEL.get(fickle, 0.0)
    p_event = max(0.0, min(100.0, SPECIAL_EVENT_BUCKET_PERCENT + bonus))
    pos_ratio = INFLUENCE_SPECIAL_EVENT_GOOD_RATIO_BY_LEVEL.get(influence, 0.50)
    p_event_pos = p_event * pos_ratio
    p_event_neg = p_event - p_event_pos

    base_neg = {k: SPECIAL_EVENT_WEIGHTS[k] for k in ("LOSE_ALL", "TRIPLE_LOSS", "DOUBLE_LOSS")}
    base_pos = {k: SPECIAL_EVENT_WEIGHTS[k] for k in ("JACKPOT_10X", "TRIPLE_WIN", "DOUBLE_WIN")}
    neg_total = sum(base_neg.values())
    pos_total = sum(base_pos.values())

    thresholds: list[tuple[float, str]] = []
    cumulative = 0.0
    for key, w in base_neg.items():
        cumulative += p_event_neg * w / neg_total if neg_total else 0.0
        thresholds.append((cumulative, key))
    for key, w in base_pos.items():
        cumulative += p_event_pos * w / pos_total if pos_total else 0.0
        thresholds.append((cumulative, key))

    remaining = max(0.0, 100.0 - p_event)
    rate = HEAVY_DIE_SINGLE_WIN_RATIO_BY_LEVEL.get(heavy, 0.50)

    cumulative += remaining * rate
    thresholds.append((cumulative, "SINGLE_WIN"))
    cumulative += remaining * (1.0 - rate)
    thresholds.append((cumulative, "SINGLE_LOSS"))

    roll = random.random() * 100.0
    for cutoff, key in thresholds:
        if roll < cutoff:
            return key
    return "SINGLE_LOSS"


def _apply_pull_to_balance(money: int, wager: int, pull: str, floor: int) -> tuple[int, bool, str]:
    """Core math: resolve a pull outcome against a balance. Returns (new_money, is_win, label)."""
    if pull == "LOSE_ALL":
        return floor, False, f"BIG LOSS reset to ${floor:,}"
    if pull == "TRIPLE_LOSS":
        return max(floor, money - 3 * wager), False, "CRITICAL LOSS (3x wager lost)"
    if pull == "DOUBLE_LOSS":
        return max(floor, money - 2 * wager), False, "HEAVY LOSS (2x wager lost)"
    if pull == "JACKPOT_10X":
        return money + 10 * wager, True, "LEGENDARY WIN (10x wager won)"
    if pull == "TRIPLE_WIN":
        return money + 3 * wager, True, "MAJOR WIN (3x wager won)"
    if pull == "DOUBLE_WIN":
        return money + 2 * wager, True, "BIG WIN (2x wager won)"
    if pull == "SINGLE_WIN":
        return money + wager, True, "WIN"
    return max(floor, money - wager), False, "LOSS"


# ─── State-producing functions (return new player dicts, never mutate input) ──

def apply_gamble(player: dict, wager: int) -> tuple[dict, str]:
    """
    Process a gamble wager. Returns (new_player_dict, result_label).
    """
    p = dict(player)
    floor = get_base_balance(p)

    # ── True Mode: pure 50/50 coin flip, step-based balance ladder ────────────
    if bool(p.get("true_mode", False)):
        is_win = random.random() < 0.5
        true_money = int(p.get("true_money", 0) or 0)
        # -1 to 1: ±1 steps. Outside that: wins double / losses halve (positive), losses double / wins halve (negative).
        if is_win:
            if true_money >= 2:
                step = true_money        # doubles: 2→4, 4→8, …
            elif true_money <= -2:
                step = abs(true_money) // 2  # halves back toward 0: -4→-2, …
            else:
                step = 1
        else:
            if true_money >= 2:
                step = true_money // 2   # halves: 8→4, 4→2, …
            elif true_money <= -2:
                step = abs(true_money)   # doubles negative: -2→-4, …
            else:
                step = 1
        delta = step if is_win else -step
        label = "WIN" if is_win else "LOSS"
        p["true_money"] = true_money + delta
        p["last_amount_change"] = delta
        p["last_multiplier"] = label
        p["true_winrate_total"] = int(p.get("true_winrate_total", 0) or 0) + 1
        if is_win:
            p["true_winrate_wins"] = int(p.get("true_winrate_wins", 0) or 0) + 1
        return p, p["last_multiplier"]

    # Use reserved pull (from Scry) if available, otherwise draw fresh
    reserved = p.get("next_pull")
    if reserved:
        pull = reserved
        p["next_pull"] = None
        p["next_pull_revealed"] = False
    else:
        pull = draw_pull(p)

    new_money, is_win, label = _apply_pull_to_balance(p["money"], wager, pull, floor)

    p["last_amount_change"] = new_money - p["money"]
    p["money"] = max(1, new_money)
    p["last_multiplier"] = label

    if is_win:
        p["win_streak"] = int(p.get("win_streak", 0) or 0) + 1
    else:
        p["win_streak"] = 0

    return p, p["last_multiplier"]


def apply_scry(player: dict) -> tuple[dict, int, str]:
    """
    Reveal the next pull by paying a % of balance.
    Returns (new_player, cost, label).  cost == -1 signals an error; label is the reason.
    """
    if player.get("next_pull") and player.get("next_pull_revealed", False):
        return player, -1, "Your next pull is already revealed. Gamble or Reroll it."

    p = dict(player)
    cost_pct = get_scry_cost_percent(p)
    cost = max(1, math.ceil(p["money"] * cost_pct / 100.0))
    p["money"] = max(1, p["money"] - cost)
    p["last_amount_change"] = -cost
    pct_str = str(int(cost_pct)) if float(cost_pct).is_integer() else str(cost_pct)
    p["last_multiplier"] = f"SCRY -{pct_str}%"
    if not p.get("next_pull"):
        p["next_pull"] = draw_pull(p)
    p["next_pull_revealed"] = True
    return p, cost, p["last_multiplier"]


def apply_reroll(player: dict) -> tuple[dict, int, str]:
    """Re-draw the next pull slot, paying a % of balance. Returns (new_player, cost, label)."""
    p = dict(player)
    ratio = get_reroll_cost_ratio(p)
    cost = max(1, math.ceil(p["money"] * ratio))
    p["money"] = max(1, p["money"] - cost)
    p["last_amount_change"] = -cost
    pct = ratio * 100.0
    pct_str = str(int(pct)) if float(pct).is_integer() else str(round(pct, 1))
    p["last_multiplier"] = f"REROLL -{pct_str}%"
    p["next_pull"] = draw_pull(p)
    p["next_pull_revealed"] = False
    return p, cost, p["last_multiplier"]


def apply_ascend(player: dict) -> tuple[dict, Optional[int], int | str]:
    """
    Prestige reset. Returns (new_player, stars_awarded, prestige_start) on success,
    or (player, None, error_message) on failure.
    """
    money = int(player.get("money", 1))
    if money < ASCEND_COST:
        return player, None, f"You need at least ${ASCEND_COST:,} to Ascend."

    stars_earned = get_ascend_stars(money)
    p = dict(player)
    p["gambler_stars"] = int(p.get("gambler_stars", 0) or 0) + stars_earned
    start = get_prestige_start_balance(p)
    p["money"] = max(1, int(start))
    p["win_streak"] = 0
    p["next_pull"] = None
    p["next_pull_revealed"] = False
    p["last_amount_change"] = p["money"] - money
    p["last_multiplier"] = f"ASCENDED (+{stars_earned} star{'s' if stars_earned != 1 else ''}, start ${start:,})"
    return p, stars_earned, start


def apply_purchase_ability(player: dict, key: str) -> tuple[dict, Optional[str]]:
    """
    Spend 1 star to advance an ability. Returns (new_player, error_msg).
    error_msg is None on success.
    """
    stars = int(player.get("gambler_stars", 0) or 0)
    if stars < 1:
        return player, "You need at least 1 Star to buy an ability."

    p = dict(player)
    abilities = dict(get_effective_abilities(p))

    if key in ABILITY_LIMITS:
        cap = ABILITY_LIMITS[key]
        current = int(abilities.get(key, 0) or 0)
        if current >= cap:
            return player, f"{key.replace('_', ' ').title()} is already maxed."
        abilities[key] = current + 1
    elif key in ("unbounded", "blessed"):
        if bool(abilities.get(key, False)):
            return player, f"{key.title()} is already owned."
        abilities[key] = True
    else:
        return player, "Unknown ability."

    p["gambler_stars"] = stars - 1
    p["ascension_abilities"] = abilities

    # Foundation immediately lifts the current balance to the new floor
    if key == "foundation":
        new_base = get_base_balance(p)
        old = int(p.get("money", 1) or 1)
        p["money"] = max(old, new_base)
        if p["money"] != old:
            p["last_amount_change"] = p["money"] - old
            p["last_multiplier"] = f"FOUNDATION floor raised to ${new_base:,}"

    return p, None


def apply_toggle_true_mode(player: dict) -> dict:
    """Toggle true mode on/off. Returns a new player dict."""
    p = dict(player)
    p["true_mode"] = not bool(player.get("true_mode", False))
    return p
