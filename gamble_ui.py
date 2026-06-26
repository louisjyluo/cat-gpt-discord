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

from gamble_constants import (
    ABILITY_LIMITS,
    ASCEND_COST,
    GREED_BASE_WIN_RATE,
    GREED_MAX_CURSED_MARKS,
    GREED_WIN_RATE_PENALTY_PER_MARK,
)
from gamble_logic import (
    get_ascend_stars,
    get_cursed_marks,
    get_effective_abilities,
    get_reroll_cost_ratio,
    get_scry_cost_percent,
    get_sins,
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

    sins = get_sins(player)
    if sins["greed"]:
        marks = get_cursed_marks(player)
        embed.add_field(name="Cursed Marks", value=str(marks), inline=True)

    next_pull = player.get("next_pull")
    revealed = player.get("next_pull_revealed", False)
    if next_pull and revealed:
        win_rate_text = "100%" if next_pull in _WIN_PULLS else "0%"
    else:
        prob = get_win_probability_percent(player)
        win_rate_text = f"{round(prob, 1)}%"
    embed.add_field(name="Win Rate", value=win_rate_text, inline=True)
    embed.add_field(name="Win Streak", value=str(player.get("win_streak", 0)), inline=True)

    change = player.get("last_amount_change", 0)
    embed.add_field(
        name="Last Change",
        value=f"+{change:,}" if change > 0 else f"{change:,}",
        inline=True,
    )
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
    envy_active = get_sins(player)["envy"]

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
    note = " *(Envy grants all tier-1 — individual purchase disabled)*" if envy_active else ""
    embed.add_field(name=f"Abilities (1 star each){note}", value="\n".join(lines), inline=False)
    if stars >= 1 and not envy_active:
        embed.set_footer(text="Click a button below to spend 1 star on that ability.")
    elif stars == 0:
        embed.set_footer(text="Ascend to earn stars, then spend them on abilities.")
    return embed


def build_sins_embed(player: dict) -> discord.Embed:
    """Sins panel embed."""
    embed = discord.Embed(title="Sins", color=discord.Color.dark_red())
    stars = int(player.get("gambler_stars", 0) or 0)
    embed.add_field(name="Stars", value=str(stars), inline=True)

    sins = get_sins(player)
    marks = get_cursed_marks(player)
    greed_rate = max(0, int(GREED_BASE_WIN_RATE) - marks * int(GREED_WIN_RATE_PENALTY_PER_MARK))

    available = [
        f"Pride {'✓' if sins['pride'] else '○'} — Disables Scry. Wins multiply your gain by current win streak.",
        f"Envy {'✓' if sins['envy'] else '○'} — Grants ALL tier-1 abilities. Big losses reset to your balance floor.",
        f"Wrath {'✓' if sins['wrath'] else '○'} — Enables the `duel` command.",
        f"Greed {'✓' if sins['greed'] else '○'} — Disables Heavy Die. Grants {int(GREED_BASE_WIN_RATE)}% win rate. Each loss adds a Cursed Mark (−2% rate). Lasts {GREED_MAX_CURSED_MARKS} losses.",
    ]
    embed.add_field(name="Available (toggle costs 1 star)", value="\n".join(available), inline=False)

    active = []
    if sins["pride"]:
        active.append("Pride — Scry disabled. Wins scaled by streak.")
    if sins["envy"]:
        active.append("Envy — All tier-1 abilities active. ENVY CURSE on big losses.")
    if sins["wrath"]:
        active.append("Wrath — Duel enabled.")
    if sins["greed"]:
        dur = max(0, int(player.get("greed_duration", 0) or 0))
        active.append(f"Greed — Win rate: {greed_rate}%. {dur} uses left. {marks} cursed mark(s).")
    if not active:
        active.append("None active.")
    embed.add_field(name="Active", value="\n".join(active), inline=False)
    return embed


def build_leaderboard_text(entries: list[dict]) -> str:
    if not entries:
        return "No gambling records yet."
    lines = ["**Gamble Leaderboard**"]
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(entries):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {p['name']} — ${p['money']:,}")
    return "\n".join(lines)


# ─── Modals ───────────────────────────────────────────────────────────────────

class GambleAmountModal(discord.ui.Modal):
    def __init__(self, on_submit):
        super().__init__(title="Gamble Amount")
        self._on_submit = on_submit
        self.amount = discord.ui.TextInput(
            label="Amount to wager",
            placeholder='Enter a number, "all", or "half"',
            required=True,
            max_length=16,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit(interaction, str(self.amount.value))


class RetributionModal(discord.ui.Modal):
    def __init__(self, on_submit, cursed_marks: int = 0):
        super().__init__(title="Retribution — Remove Cursed Marks")
        self._on_submit = on_submit
        self.stars_input = discord.ui.TextInput(
            label=f"Stars to spend ({cursed_marks} mark(s) available)",
            placeholder="Enter a number",
            required=True,
            max_length=4,
        )
        self.add_item(self.stars_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit(interaction, str(self.stars_input.value))


class DuelChallengeModal(discord.ui.Modal):
    def __init__(self, on_submit):
        super().__init__(title="Challenge to a Duel")
        self._on_submit = on_submit
        self.opponent_input = discord.ui.TextInput(
            label="Opponent (@mention or user ID)",
            placeholder="@username or 123456789",
            required=True,
            max_length=64,
        )
        self.add_item(self.opponent_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit(interaction, str(self.opponent_input.value))


# ─── Views ────────────────────────────────────────────────────────────────────

class GambleView(discord.ui.View):
    """
    Main gamble panel. Handlers:
      on_gamble(interaction, wager_str)  — called for Amount/Half/All
      on_scry(interaction)
      on_reroll(interaction)
      on_menu(interaction)
      on_retribution_submit(interaction, stars_str)  — optional
    """

    def __init__(self, player: dict, *, on_gamble, on_scry, on_reroll, on_menu,
                 on_retribution_submit=None):
        super().__init__(timeout=None)
        self._on_gamble = on_gamble
        self._on_scry = on_scry
        self._on_reroll = on_reroll
        self._on_menu = on_menu
        self._on_retribution_submit = on_retribution_submit

        scry_pct = _fmt_pct(get_scry_cost_percent(player))
        reroll_pct = _fmt_pct(get_reroll_cost_ratio(player) * 100.0)
        sins = get_sins(player)
        marks = get_cursed_marks(player)
        stars = int(player.get("gambler_stars", 0) or 0)

        # Patch labels and disabled states onto the static buttons
        for item in self.children:
            cid = getattr(item, "custom_id", None)
            if cid == "g_scry":
                item.label = f"Scry ({scry_pct}%)"
                item.disabled = sins["pride"]
            elif cid == "g_reroll":
                item.label = f"Reroll ({reroll_pct}%)"
            elif cid == "g_retribution":
                item.disabled = not (marks > 0 and stars > 0)

        self._cursed_marks = marks

    @discord.ui.button(label="Amount", style=discord.ButtonStyle.primary, custom_id="g_amount", row=0)
    async def btn_amount(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GambleAmountModal(self._on_gamble)
        )

    @discord.ui.button(label="Half", style=discord.ButtonStyle.primary, custom_id="g_half", row=0)
    async def btn_half(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_gamble(interaction, "half")

    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, custom_id="g_all", row=0)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_gamble(interaction, "all")

    @discord.ui.button(label="Scry (?%)", style=discord.ButtonStyle.success, custom_id="g_scry", row=1)
    async def btn_scry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_scry(interaction)

    @discord.ui.button(label="Reroll (?%)", style=discord.ButtonStyle.success, custom_id="g_reroll", row=1)
    async def btn_reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_reroll(interaction)

    @discord.ui.button(label="Retribution", style=discord.ButtonStyle.danger, custom_id="g_retribution", row=1)
    async def btn_retribution(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._on_retribution_submit:
            await interaction.response.send_modal(
                RetributionModal(self._on_retribution_submit, cursed_marks=self._cursed_marks)
            )
        else:
            await interaction.response.send_message("Retribution not available.", ephemeral=True)

    @discord.ui.button(label="Menu", style=discord.ButtonStyle.secondary, custom_id="g_menu", row=2)
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_menu(interaction)


class GambleMenuView(discord.ui.View):
    """
    Menu panel with exactly three options plus a back button.
    Handlers:
      on_leaderboard(interaction)
      on_ascension(interaction)
      on_sins(interaction)
      on_back(interaction)
    """

    def __init__(self, *, on_leaderboard, on_ascension, on_sins, on_back):
        super().__init__(timeout=None)
        self._on_leaderboard = on_leaderboard
        self._on_ascension = on_ascension
        self._on_sins = on_sins
        self._on_back = on_back

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary, custom_id="m_leaderboard", row=0)
    async def btn_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_leaderboard(interaction)

    @discord.ui.button(label="Ascension", style=discord.ButtonStyle.success, custom_id="m_ascension", row=0)
    async def btn_ascension(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_ascension(interaction)

    @discord.ui.button(label="Sins", style=discord.ButtonStyle.danger, custom_id="m_sins", row=0)
    async def btn_sins(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_sins(interaction)

    @discord.ui.button(label="Back to Game", style=discord.ButtonStyle.secondary, custom_id="m_back", row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_back(interaction)


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
        envy_active = get_sins(player)["envy"]
        stars = int(player.get("gambler_stars", 0) or 0)
        money = int(player.get("money", 0) or 0)
        can_buy = stars >= 1 and not envy_active

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


class SinsView(discord.ui.View):
    """
    Sins panel. on_toggle_sin(interaction, key: str)
    """

    def __init__(self, player: dict, *, on_toggle_sin):
        super().__init__(timeout=600)
        self._on_toggle_sin = on_toggle_sin

        sins = get_sins(player)
        stars = int(player.get("gambler_stars", 0) or 0)

        for key in ("pride", "envy", "wrath", "greed"):
            active = sins[key]
            button = discord.ui.Button(
                label=f"{key.title()} {'✓' if active else '○'}",
                style=discord.ButtonStyle.secondary if active else discord.ButtonStyle.danger,
                custom_id=f"sin_{key}",
                row=0,
                disabled=stars < 1,
            )

            async def _cb(interaction: discord.Interaction, k=key):
                await self._on_toggle_sin(interaction, k)

            button.callback = _cb
            self.add_item(button)
