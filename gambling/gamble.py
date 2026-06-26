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

import re
import time

import discord

from db import get_gamble_leaderboard
from .gamble_constants import ASCEND_COST, GREED_MAX_CURSED_MARKS
from .gamble_logic import (
    apply_ascend,
    apply_gamble,
    apply_purchase_ability,
    apply_reroll,
    apply_retribution,
    apply_scry,
    apply_toggle_sin,
    get_base_balance,
    get_cursed_marks,
    get_gamble_cooldown,
    get_sins,
    resolve_duel,
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
    GambleAmountModal,
    GambleMenuView,
    GambleView,
    SinsView,
    build_ascension_embed,
    build_gamble_embed,
    build_leaderboard_text,
    build_menu_embed,
    build_sins_embed,
)

# Re-export for cat-gpt.py
__all__ = ["send_gamble_panel", "send_duel_command", "load_gamble_database", "save_gamble_database"]


# ─── Panel helpers ────────────────────────────────────────────────────────────

def _make_gamble_view(player: dict) -> GambleView:
    return GambleView(
        player,
        on_gamble=_on_gamble,
        on_scry=_on_scry,
        on_reroll=_on_reroll,
        on_menu=_on_menu,
        on_retribution_submit=_on_retribution_submit,
    )


async def _show_gamble_panel(interaction: discord.Interaction, player: dict, *, content: str = ""):
    """Edit the current interaction message to show the gamble panel."""
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
    if player.get("next_pull_revealed") and raw not in ("all", "half"):
        await interaction.response.send_message(
            "Custom amounts are disabled after Scry — use Half, All, or Reroll.",
            ephemeral=True,
        )
        return
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


async def _on_retribution_submit(interaction: discord.Interaction, stars_str: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Retribution only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    try:
        spend = max(0, int(stars_str.strip()))
    except (ValueError, TypeError):
        await interaction.response.send_message("Enter a valid number of stars.", ephemeral=True)
        return

    new_player, err = apply_retribution(player, spend)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    removed = get_cursed_marks(player) - get_cursed_marks(new_player)
    await interaction.response.send_message(
        f"Removed {removed} Cursed Mark(s). Remaining: {get_cursed_marks(new_player)}.",
        ephemeral=True,
    )
    # Refresh the panel
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
        on_sins=_on_menu_sins,
        on_back=_on_menu_back,
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


# ─── Sins ─────────────────────────────────────────────────────────────────────

async def _on_menu_sins(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    view = SinsView(player, on_toggle_sin=_on_toggle_sin)
    await interaction.response.send_message(
        embed=build_sins_embed(player),
        view=view,
        ephemeral=True,
    )


async def _on_toggle_sin(interaction: discord.Interaction, key: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Only works in a server.", ephemeral=True)
        return

    player = get_or_create_player(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    new_player, err = apply_toggle_sin(player, key)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    save_player(interaction.user.id, str(interaction.guild_id), new_player)
    view = SinsView(new_player, on_toggle_sin=_on_toggle_sin)
    await interaction.response.edit_message(
        content=f"{key.title()} toggled.",
        embed=build_sins_embed(new_player),
        view=view,
    )


# ─── Duel (text command, requires Wrath) ─────────────────────────────────────

async def send_duel_command(msg: discord.Message, opponent_input: str) -> None:
    if msg.guild is None:
        await msg.reply("Duels only work in a server.")
        return

    challenger = get_or_create_player(msg.guild.id, msg.author.id, msg.author.display_name)
    if not get_sins(challenger)["wrath"]:
        await msg.reply("You need the Wrath sin active to duel.")
        return

    match = re.search(r"\d{15,20}", opponent_input.strip())
    if not match:
        await msg.reply("Could not find a valid user mention or ID. Usage: `duel @user`")
        return

    opponent_id = int(match.group(0))
    if opponent_id == msg.author.id:
        await msg.reply("You can't duel yourself.")
        return

    try:
        member = msg.guild.get_member(opponent_id) or await msg.guild.fetch_member(opponent_id)
    except Exception:
        await msg.reply("Could not find that user in this server.")
        return

    opponent = get_or_create_player(msg.guild.id, opponent_id, member.display_name)

    winner, c_roll, o_roll, c_max = resolve_duel(challenger, opponent)
    c_name, o_name = msg.author.display_name, member.display_name

    if winner == "challenger":
        loser, loser_id, loser_name, winner_name = opponent, opponent_id, o_name, c_name
    else:
        loser, loser_id, loser_name, winner_name = challenger, msg.author.id, c_name, o_name

    old_money = int(loser.get("money", 1))
    floor = get_base_balance(loser)
    new_loser = dict(loser)
    new_loser["money"] = floor
    new_loser["last_amount_change"] = floor - old_money
    new_loser["last_multiplier"] = "DUEL LOSS"
    new_loser["win_streak"] = 0
    save_player(loser_id, str(msg.guild.id), new_loser)

    o_balance = int(opponent.get("money", 1))
    lines = [
        f"**DUEL** — {c_name} vs {o_name}",
        "",
        f"{c_name} rolled **{c_roll:,.1f}** / {c_max:,.0f}",
        f"{o_name} rolled **{o_roll:,.1f}** / {o_balance:,}",
        "",
        f"**{winner_name}** wins!",
        f"**{loser_name}** resets to ${floor:,}.",
    ]
    await msg.reply("\n".join(lines))


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
    await msg.reply(welcome, embed=build_gamble_embed(player), view=_make_gamble_view(player))
