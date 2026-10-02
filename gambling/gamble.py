"""
gamble.py
─────────
Thin command layer — Discord I/O only.

Pattern for every interaction:
  1. get_or_create_player(...)
  2. apply_*(player, ...) from gamble_logic  → new player dict, optional error
  3. save_player(...)
  4. respond / refresh panel

No game rules live here. No direct MongoDB calls.
"""
from __future__ import annotations

import time

import discord

from db import get_gamble_leaderboard, get_true_leaderboard
from .gamble_constants import ASCEND_COST
from .gamble_logic import (
    apply_ascend,
    apply_gamble,
    apply_purchase_ability,
    apply_reroll,
    apply_scry,
    apply_toggle_true_mode,
    get_base_balance,
    get_gamble_cooldown,
)
from .gamble_state import (
    get_last_gamble_at,
    get_or_create_player,
    load_gamble_database,
    save_gamble_database,
    save_player,
    set_last_gamble_at,
)
from .gamble_ui import (
    AscendConfirmView,
    AscensionView,
    GambleMenuView,
    GambleView,
    TrueGambleView,
    build_ascension_embed,
    build_gamble_embed,
    build_leaderboard_text,
    build_menu_embed,
    build_true_gamble_embed,
    build_true_leaderboard_text,
)

# Re-export for cat-gpt.py
__all__ = ["send_gamble_panel", "load_gamble_database", "save_gamble_database"]


# ─── Panel helpers ────────────────────────────────────────────────────────────

def _make_gamble_view(player: dict) -> GambleView:
    return GambleView(
        player,
        on_gamble=_on_gamble,
        on_scry=_on_scry,
        on_reroll=_on_reroll,
        on_menu=_on_menu,
    )


def _make_true_gamble_view(player: dict) -> TrueGambleView:
    return TrueGambleView(on_roll=_on_true_roll, on_menu=_on_menu, on_leaderboard=_on_true_leaderboard)


async def _show_gamble_panel(interaction: discord.Interaction, player: dict, *, content: str = ""):
    """Edit the current interaction message to show the gamble panel."""
    if bool(player.get("true_mode", False)):
        embed = build_true_gamble_embed(player)
        view = _make_true_gamble_view(player)
    else:
        embed = build_gamble_embed(player)
        view = _make_gamble_view(player)
    try:
        await interaction.response.edit_message(content=content, embed=embed, view=view)
    except discord.InteractionResponded:
        if interaction.message:
            await interaction.message.edit(content=content, embed=embed, view=view)
        else:
            await interaction.followup.send(content=content, embed=embed, view=view)


# ─── Base game actions ────────────────────────────────────────────────────────

async def _on_gamble(interaction: discord.Interaction, wager_str: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Gamble only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)

    # Wager parsing
    raw = wager_str.strip().lower()
    true_mode = bool(player.get("true_mode", False))
    if player.get("next_pull_revealed") and not true_mode and raw not in ("all", "half"):
        await interaction.response.send_message(
            "Custom amounts are disabled after Scry — use Half, All, or Reroll.",
            ephemeral=True,
        )
        return
    if true_mode:
        true_money = int(player.get("true_money", 0) or 0)
        if raw == "all":
            wager = max(1, true_money) if true_money > 0 else 100
        elif raw == "half":
            wager = max(1, true_money // 2) if true_money > 0 else 50
        else:
            try:
                wager = int(raw)
            except ValueError:
                await interaction.response.send_message('Enter a number, "all", or "half".', ephemeral=True)
                return
        if wager <= 0:
            await interaction.response.send_message("Wager must be greater than 0.", ephemeral=True)
            return
    else:
        if raw == "all":
            wager = player["money"]
        elif raw == "half":
            wager = max(1, player["money"] // 2)
        else:
            try:
                wager = int(raw)
            except ValueError:
                await interaction.response.send_message('Enter a number, "all", or "half".', ephemeral=True)
                return
        if wager <= 0:
            await interaction.response.send_message("Wager must be greater than 0.", ephemeral=True)
            return
        if wager > player["money"]:
            await interaction.response.send_message(f"You only have ${player['money']:,}.", ephemeral=True)
            return

    # Cooldown check
    now = time.monotonic()
    cooldown = get_gamble_cooldown(player)
    last_at = get_last_gamble_at(interaction.user.id)
    if last_at is not None:
        retry = cooldown - (now - last_at)
        if retry > 0:
            await interaction.response.send_message(
                f"Cool down — try again in {round(retry, 2)}s.", ephemeral=True
            )
            return
    set_last_gamble_at(interaction.user.id, now)

    new_player, label = apply_gamble(player, wager)
    save_player(interaction.user.id, str(interaction.guild_id), new_player)

    await interaction.response.defer()
    await _show_gamble_panel(interaction, new_player)


async def _on_scry(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Scry only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    if player["money"] < 15:
        await interaction.response.send_message("You need at least $15 to Scry.", ephemeral=True)
        return

    new_player, cost, err = apply_scry(player)
    if cost == -1:
        await interaction.response.send_message(err, ephemeral=True)
        return

    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    await interaction.response.defer()
    await _show_gamble_panel(interaction, new_player)


async def _on_reroll(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Reroll only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    if player["money"] < 10:
        await interaction.response.send_message("You need at least $10 to Reroll.", ephemeral=True)
        return

    new_player, cost, label = apply_reroll(player)
    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    await interaction.response.defer()
    await _show_gamble_panel(interaction, new_player)


# ─── Menu ─────────────────────────────────────────────────────────────────────

async def _on_menu(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Menu only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    menu_view = GambleMenuView(
        on_leaderboard=_on_menu_leaderboard,
        on_ascension=_on_menu_ascension,
        on_back=_on_menu_back,
        on_true_mode=_on_toggle_true_mode,
        player=player,
    )
    await interaction.response.edit_message(
        content="",
        embed=build_menu_embed(player),
        view=menu_view,
    )


async def _on_menu_back(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return
    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    await _show_gamble_panel(interaction, player)


async def _on_menu_leaderboard(interaction: discord.Interaction) -> None:
    entries = get_gamble_leaderboard(interaction.guild_id, limit=5)
    await interaction.response.send_message(build_leaderboard_text(entries), ephemeral=True)


# ─── Ascension ────────────────────────────────────────────────────────────────

async def _on_menu_ascension(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    view = AscensionView(player, on_buy_ability=_on_buy_ability, on_ascend=_on_ascend_request)
    await interaction.response.send_message(
        embed=build_ascension_embed(player),
        view=view,
        ephemeral=True,
    )


async def _on_buy_ability(interaction: discord.Interaction, key: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    new_player, err = apply_purchase_ability(player, key)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    view = AscensionView(new_player, on_buy_ability=_on_buy_ability, on_ascend=_on_ascend_request)
    await interaction.response.edit_message(
        content=f"Purchased {key.replace('_', ' ').title()}.",
        embed=build_ascension_embed(new_player),
        view=view,
    )


async def _on_ascend_request(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    money = int(player.get("money", 1))
    if money < ASCEND_COST:
        await interaction.response.send_message(f"You need ${ASCEND_COST:,} to Ascend.", ephemeral=True)
        return

    confirm_view = AscendConfirmView(on_confirm=_on_ascend_confirm)
    await interaction.response.edit_message(
        content=f"Ascending will reset your balance. You'll receive stars based on ${money:,}. Confirm?",
        embed=None,
        view=confirm_view,
    )


async def _on_ascend_confirm(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    new_player, stars_earned, result = apply_ascend(player)
    if stars_earned is None:
        # result is an error string
        await interaction.response.edit_message(content=str(result), view=None, embed=None)
        return

    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    await interaction.response.edit_message(
        content=f"Ascended! +{stars_earned} star(s). New balance: ${int(result):,}.",
        view=None,
        embed=None,
    )
    try:
        if interaction.guild and interaction.channel:
            await interaction.channel.send(f"✨ {interaction.user.display_name} has ascended!")
    except Exception:
        pass


async def _on_toggle_true_mode(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    new_player = apply_toggle_true_mode(player)
    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    await interaction.response.defer()
    await _show_gamble_panel(interaction, new_player)


async def _on_true_leaderboard(interaction: discord.Interaction) -> None:
    entries = get_true_leaderboard(interaction.guild_id, limit=5)
    await interaction.response.send_message(build_true_leaderboard_text(entries), ephemeral=True)


async def _on_true_roll(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)

    now = time.monotonic()
    cooldown = get_gamble_cooldown(player)
    last_at = get_last_gamble_at(interaction.user.id)
    if last_at is not None:
        retry = cooldown - (now - last_at)
        if retry > 0:
            await interaction.response.send_message(
                f"Cool down — try again in {round(retry, 2)}s.", ephemeral=True
            )
            return
    set_last_gamble_at(interaction.user.id, now)

    new_player, label = apply_gamble(player, 0)  # wager unused in true mode
    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    await interaction.response.defer()
    await _show_gamble_panel(interaction, new_player)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def send_gamble_panel(msg: discord.Message) -> None:
    if msg.guild is None:
        await msg.reply("Gamble only works in a server.")
        return

    player = get_or_create_player(msg.guild.id, msg.author.id, msg.author.display_name)
    welcome = (
        "Welcome to the Catgpt Gamble Game! Use the buttons below to start gambling."
        if player["money"] == 1
        else "Welcome back! Use the buttons below to keep gambling."
    )
    if bool(player.get("true_mode", False)):
        await msg.reply(welcome, embed=build_true_gamble_embed(player), view=_make_true_gamble_view(player))
    else:
        await msg.reply(welcome, embed=build_gamble_embed(player), view=_make_gamble_view(player))
