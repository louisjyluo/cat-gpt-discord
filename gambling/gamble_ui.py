"""
gamble_ui.py
────────────
Discord embeds and Views for the gamble game.

Views hold NO game logic — they render player state and dispatch to
handler callables supplied by gamble.py. All callbacks follow the
async signature:  handler(interaction, **kwargs)
"""
from __future__ import annotations

import discord

from .gamble_constants import (
    ABILITY_LIMITS,
    ASCEND_COST,
)
from .gamble_logic import (
    get_ascend_stars,
    get_effective_abilities,
    get_reroll_cost_ratio,
    get_scry_cost_percent,
    get_win_probability_percent,
    pull_label,
)


# ─── Formatting helpers ───────────────────────────────────────────────────────

def _fmt_pct(value: float) -> str:
    v = round(float(value), 2)
    return str(int(v)) if v == int(v) else str(v).rstrip("0").rstrip(".")


_WIN_PULLS = {"JACKPOT_10X", "TRIPLE_WIN", "DOUBLE_WIN", "SINGLE_WIN"}


# ─── Embeds ──────────────────────────────────────────────────────────────────

def build_gamble_embed(player: dict) -> discord.Embed:
    """Main gamble panel embed."""
    embed = discord.Embed(title="Catgpt Gamble Game", color=discord.Color.gold())
    embed.add_field(name="Player", value=player["name"], inline=False)
    embed.add_field(name="Balance", value=f"${player['money']:,}", inline=True)

    next_pull = player.get("next_pull")
    revealed = player.get("next_pull_revealed", False)
    if next_pull and revealed:
        win_rate_text = "100%" if next_pull in _WIN_PULLS else "0%"
    else:
        prob = get_win_probability_percent(player)
        win_rate_text = f"{round(prob, 1)}%"
    embed.add_field(name="Win Rate", value=win_rate_text, inline=True)
    embed.add_field(name="Last Result", value=str(player.get("last_multiplier", "N/A")), inline=True)
    embed.add_field(
        name="Next Pull",
        value=pull_label(next_pull) if next_pull and revealed else "Hidden",
        inline=True,
    )
    return embed


def build_menu_embed(player: dict) -> discord.Embed:
    """Gamble menu embed (shown when the Menu button is pressed)."""
    embed = discord.Embed(title="Gamble Menu", color=discord.Color.blurple())
    embed.add_field(name="Player", value=player.get("name", "Unknown"), inline=True)
    embed.add_field(name="Balance", value=f"${player.get('money', 0):,}", inline=True)
    stars = int(player.get("gambler_stars", 0) or 0)
    embed.add_field(name="Stars", value=str(stars), inline=True)
    embed.description = "Choose an option below."
    return embed


def build_ascension_embed(player: dict) -> discord.Embed:
    """
    Unified ascension embed: shows stars, all abilities, and ascend eligibility.
    """
    embed = discord.Embed(title="Ascension", color=discord.Color.gold())
    stars = int(player.get("gambler_stars", 0) or 0)
    money = int(player.get("money", 0) or 0)
    embed.add_field(name="Stars", value=str(stars), inline=True)

    stars_on_ascend = get_ascend_stars(money)
    if money >= ASCEND_COST:
        embed.add_field(
            name="Ascend (available)",
            value=f"Spend ${ASCEND_COST:,} → +{stars_on_ascend} star(s). Your balance resets to your prestige floor.",
            inline=False,
        )
    else:
        embed.add_field(
            name="Ascend (locked)",
            value=f"Requires ${ASCEND_COST:,}. You have ${money:,}.",
            inline=False,
        )

    abilities = get_effective_abilities(player)

    lines = [
        f"Foundation {min(5, int(abilities.get('foundation', 0) or 0))}/5 — Raises your balance floor.",
        f"Fickle {min(2, int(abilities.get('fickle', 0) or 0))}/2 — Events happen more often.",
        f"Influence {min(3, int(abilities.get('influence', 0) or 0))}/3 — Events lean positive.",
        f"Heavy Die {min(3, int(abilities.get('heavy_die', 0) or 0))}/3 — Better base win rate.",
        f"Sage {min(3, int(abilities.get('sage', 0) or 0))}/3 — Cheaper Scry.",
        f"Passion {min(3, int(abilities.get('passion', 0) or 0))}/3 — Shorter gamble cooldown.",
        f"Unbounded {1 if abilities.get('unbounded') else 0}/1 — Halves Reroll cost.",
        f"Blessed {1 if abilities.get('blessed') else 0}/1 — Start each life with $1,000.",
    ]
    embed.add_field(name="Abilities (1 star each)", value="\n".join(lines), inline=False)
    if stars >= 1:
        embed.set_footer(text="Click a button below to spend 1 star on that ability.")
    else:
        embed.set_footer(text="Ascend to earn stars, then spend them on abilities.")
    return embed


def build_true_leaderboard_text(entries: list[dict]) -> str:
    if not entries:
        return "No True Mode records yet."
    lines = ["**True Mode Leaderboard**"]
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(entries):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        tm = p['true_money']
        tm_str = f"${tm:,}" if tm >= 0 else f"-${abs(tm):,}"
        wins = p['true_winrate_wins']
        total = p['true_winrate_total']
        pct = round(100.0 * wins / total, 1) if total > 0 else 0.0
        lines.append(f"{prefix} {p['name']} — {tm_str} | {wins}/{total} ({pct}%)")
    return "\n".join(lines)


def build_leaderboard_text(entries: list[dict]) -> str:
    if not entries:
        return "No gambling records yet."
    lines = ["**Gamble Leaderboard**"]
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(entries):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {p['name']} — ${p['money']:,}")
    return "\n".join(lines)

def build_true_gamble_embed(player: dict) -> discord.Embed:
    """True mode panel embed — ladder balance, win rate, no abilities."""
    embed = discord.Embed(title="True Mode", color=discord.Color.teal())
    embed.add_field(name="Player", value=player["name"], inline=False)

    true_money = int(player.get("true_money", 0) or 0)
    tm_str = f"${true_money:,}" if true_money >= 0 else f"-${abs(true_money):,}"
    embed.add_field(name="True Balance", value=tm_str, inline=True)

    true_wins = int(player.get("true_winrate_wins", 0) or 0)
    true_total = int(player.get("true_winrate_total", 0) or 0)
    if true_total > 0:
        true_pct = round(100.0 * true_wins / true_total, 1)
        true_wr_text = f"{true_wins}/{true_total} ({true_pct}%)"
    else:
        true_wr_text = "No data"
    embed.add_field(name="True Win Rate", value=true_wr_text, inline=True)
    embed.add_field(name="Last Result", value=str(player.get("last_multiplier", "N/A")), inline=True)
    return embed

# ─── Views ────────────────────────────────────────────────────────────────────

class GambleView(discord.ui.View):
    """
    Main gamble panel. Handlers:
      on_gamble(interaction, wager_str)  — called for Amount/Half/All
      on_scry(interaction)
      on_reroll(interaction)
      on_menu(interaction)
    """

    def __init__(self, player: dict, *, on_gamble, on_scry, on_reroll, on_menu):
        super().__init__(timeout=None)
        self._on_gamble = on_gamble
        self._on_scry = on_scry
        self._on_reroll = on_reroll
        self._on_menu = on_menu

        scry_pct = _fmt_pct(get_scry_cost_percent(player))
        reroll_pct = _fmt_pct(get_reroll_cost_ratio(player) * 100.0)
        true_mode = bool(player.get("true_mode", False))

        # Patch labels and disabled states onto the static buttons
        for item in self.children:
            cid = getattr(item, "custom_id", None)
            if cid == "g_scry":
                item.label = f"Scry ({scry_pct}%)"
                item.disabled = true_mode
            elif cid == "g_reroll":
                item.label = f"Reroll ({reroll_pct}%)"
                item.disabled = true_mode

    @discord.ui.button(label="Half", style=discord.ButtonStyle.primary, custom_id="g_half", row=0)
    async def btn_half(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_gamble(interaction, "half")

    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, custom_id="g_all", row=0)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_gamble(interaction, "all")

    @discord.ui.button(label="Scry (?%)", style=discord.ButtonStyle.success, custom_id="g_scry", row=0)
    async def btn_scry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_scry(interaction)

    @discord.ui.button(label="Reroll (?%)", style=discord.ButtonStyle.success, custom_id="g_reroll", row=0)
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_reroll(interaction)

    @discord.ui.button(label="Menu", style=discord.ButtonStyle.secondary, custom_id="g_menu", row=0)
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_menu(interaction)


class GambleMenuView(discord.ui.View):
    """
    Menu panel with exactly three options plus a back button.
    Handlers:
      on_leaderboard(interaction)
      on_ascension(interaction)
      on_back(interaction)
      on_true_mode(interaction)  — optional
    """

    def __init__(self, *, on_leaderboard, on_ascension, on_back,
                 on_true_mode=None, player=None):
        super().__init__(timeout=None)
        self._on_leaderboard = on_leaderboard
        self._on_ascension = on_ascension
        self._on_back = on_back
        self._on_true_mode = on_true_mode

        true_mode = bool((player or {}).get("true_mode", False))
        for item in self.children:
            if getattr(item, "custom_id", None) == "m_true_mode":
                item.label = "True Mode \u2713" if true_mode else "True Mode \u25cb"
                item.style = discord.ButtonStyle.success if true_mode else discord.ButtonStyle.secondary

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary, custom_id="m_leaderboard", row=0)
    async def btn_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_leaderboard(interaction)

    @discord.ui.button(label="Ascension", style=discord.ButtonStyle.success, custom_id="m_ascension", row=0)
    async def btn_ascension(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_ascension(interaction)

    @discord.ui.button(label="Back to Game", style=discord.ButtonStyle.secondary, custom_id="m_back", row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_back(interaction)

    @discord.ui.button(label="True Mode \u25cb", style=discord.ButtonStyle.secondary, custom_id="m_true_mode", row=1)
    async def btn_true_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._on_true_mode:
            await self._on_true_mode(interaction)


class TrueGambleView(discord.ui.View):
    """True mode panel — Roll, Leaderboard, and Menu."""

    def __init__(self, *, on_roll, on_menu, on_leaderboard):
        super().__init__(timeout=None)
        self._on_roll = on_roll
        self._on_menu = on_menu
        self._on_leaderboard = on_leaderboard

    @discord.ui.button(label="Roll", style=discord.ButtonStyle.primary, custom_id="tg_roll", row=0)
    async def btn_roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_roll(interaction)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary, custom_id="tg_leaderboard", row=0)
    async def btn_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_leaderboard(interaction)

    @discord.ui.button(label="Menu", style=discord.ButtonStyle.secondary, custom_id="tg_menu", row=0)
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_menu(interaction)


class AscensionView(discord.ui.View):
    """
    Unified ascension panel: ability purchase buttons + ascend button.
    on_buy_ability(interaction, key: str)
    on_ascend(interaction)
    """

    def __init__(self, player: dict, *, on_buy_ability, on_ascend):
        super().__init__(timeout=600)
        self._on_buy_ability = on_buy_ability
        self._on_ascend = on_ascend

        abilities = get_effective_abilities(player)
        stars = int(player.get("gambler_stars", 0) or 0)
        money = int(player.get("money", 0) or 0)
        can_buy = stars >= 1

        # Ability buy buttons (row 0 and 1)
        ability_defs = [
            ("Foundation", "foundation", ABILITY_LIMITS["foundation"], 0),
            ("Fickle", "fickle", ABILITY_LIMITS["fickle"], 0),
            ("Influence", "influence", ABILITY_LIMITS["influence"], 0),
            ("Heavy Die", "heavy_die", ABILITY_LIMITS["heavy_die"], 0),
            ("Sage", "sage", ABILITY_LIMITS["sage"], 0),
            ("Passion", "passion", ABILITY_LIMITS["passion"], 1),
            ("Unbounded", "unbounded", 1, 1),
            ("Blessed", "blessed", 1, 1),
        ]
        for label, key, cap, row in ability_defs:
            if key in ABILITY_LIMITS:
                current = int(abilities.get(key, 0) or 0)
                maxed = current >= cap
                btn_label = f"{label} {current}/{cap}"
            else:
                owned = bool(abilities.get(key, False))
                maxed = owned
                btn_label = f"{label} {1 if owned else 0}/1"

            button = discord.ui.Button(
                label=btn_label,
                style=discord.ButtonStyle.secondary if maxed else discord.ButtonStyle.primary,
                custom_id=f"asc_{key}",
                row=row,
                disabled=not (can_buy and not maxed),
            )

            async def _cb(interaction: discord.Interaction, k=key):
                await self._on_buy_ability(interaction, k)

            button.callback = _cb
            self.add_item(button)

        # Ascend button (row 2)
        ascend_btn = discord.ui.Button(
            label=f"Ascend (${ASCEND_COST:,})",
            style=discord.ButtonStyle.danger,
            custom_id="asc_ascend",
            row=2,
            disabled=money < ASCEND_COST,
        )
        async def _ascend_cb(interaction: discord.Interaction):
            await self._on_ascend(interaction)
        ascend_btn.callback = _ascend_cb
        self.add_item(ascend_btn)


class AscendConfirmView(discord.ui.View):
    """Confirmation dialog before ascending."""

    def __init__(self, on_confirm):
        super().__init__(timeout=30)
        self._on_confirm = on_confirm

    @discord.ui.button(label="Confirm Ascend", style=discord.ButtonStyle.danger, custom_id="asc_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="asc_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None, embed=None)



