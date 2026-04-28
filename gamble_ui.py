import discord
from gamble_constants import REROLL_COST_PERCENT, SCRY_COST_BY_SAGE


def _abilities_or_default(player):
  abilities = player.get("ascension_abilities")
  return abilities if isinstance(abilities, dict) else {}


def _has_any_unlocked_abilities(player):
  abilities = _abilities_or_default(player)
  return any(
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


def _format_percent(value):
  normalized = round(float(value), 2)
  if normalized.is_integer():
    return str(int(normalized))
  return str(normalized).rstrip("0").rstrip(".")


def _scry_cost_percent(player):
  abilities = _abilities_or_default(player)
  sage = int(abilities.get("sage", 0) or 0)
  return SCRY_COST_BY_SAGE.get(sage, 20.0)


def _reroll_cost_percent(player):
  abilities = _abilities_or_default(player)
  cost = REROLL_COST_PERCENT
  if bool(abilities.get("unbounded", False)):
    cost = cost / 2.0
  return cost


def build_ascension_abilities_embed(player):
  embed = discord.Embed(title="Ascension Abilities", color=discord.Color.gold())
  stars = int(player.get("gambler_stars", 0) or 0)
  embed.add_field(name="Stars - Each ability costs 1 Star.", value=str(max(0, stars)), inline=True)

  abilities = _abilities_or_default(player)
  greed = bool(abilities.get("greed", False))

  if stars <= 0 and not _has_any_unlocked_abilities(player):
    embed.description = "You must ascend once to see the abilities page."
    return embed

  show_catalog = stars > 0
  if greed:
    foundation = 1
    fickle = 1
    influence = 1
    heavy_die = 1
    sage = 1
    passion = 1
    unbounded = True
    blessed = True
  else:
    foundation = int(abilities.get("foundation", 0) or 0)
    fickle = int(abilities.get("fickle", 0) or 0)
    influence = int(abilities.get("influence", 0) or 0)
    heavy_die = int(abilities.get("heavy_die", 0) or 0)
    sage = int(abilities.get("sage", 0) or 0)
    passion = int(abilities.get("passion", 0) or 0)
    unbounded = bool(abilities.get("unbounded", False))
    blessed = bool(abilities.get("blessed", False))

  owned_lines = []
  if show_catalog:
    owned_lines = [
      f"Foundation: {max(0, min(5, foundation))}/5 - Raises your base balance floor.",
      f"Fickle: {max(0, min(2, fickle))}/2 - Events happen more often (both good and bad).",
      f"Influence: {max(0, min(3, influence))}/3 - Events are weighted toward good events.",
      f"Heavy Die: {max(0, min(3, heavy_die))}/3 - Improves your normal win rate.",
      f"Sage: {max(0, min(3, sage))}/3 - Reduces the % cost of Scry.",
      f"Passion: {max(0, min(3, passion))}/3 - Lowers the cooldown between gambles.",
      f"Unbounded: {1 if unbounded else 0}/1 - Halves the % cost of Reroll.",
      f"Blessed: {1 if blessed else 0}/1 - start each new life with $1000.",
      f"Greed: {1 if greed else 0}/1 - Grants ALL tier 1 perks, but beware of the consequences...",
    ]
  else:
    if foundation > 0:
      owned_lines.append(f"Foundation: {foundation}/5 - Raises your base balance floor.")
    if fickle > 0:
      owned_lines.append(f"Fickle: {fickle}/2 - Events happen more often (both good and bad).")
    if influence > 0:
      owned_lines.append(f"Influence: {influence}/3 - Events are weighted toward good events.")
    if heavy_die > 0:
      owned_lines.append(f"Heavy Die: {heavy_die}/3 - Improves your normal win rate.")
    if sage > 0:
      owned_lines.append(f"Sage: {sage}/3 - Reduces the % cost of Scry.")
    if passion > 0:
      owned_lines.append(f"Passion: {passion}/3 - Lowers the cooldown between gambles.")
    if unbounded:
      owned_lines.append("Unbounded: 1/1 - Halves the % cost of Reroll.")
    if blessed:
      owned_lines.append("Blessed: 1/1 - start each new life with $1000.")
    if greed:
      owned_lines.append("Greed: 1/1 - Grants ALL tier 1 perks, but beware of the consequences...")

  if not owned_lines:
    owned_lines = ["You must ascend once to see the abilities page."]
  embed.add_field(name="Current", value="\n".join(owned_lines), inline=False)
  return embed


def build_gamble_menu_embed(player):
  embed = discord.Embed(title="Gamble Menu", color=discord.Color.gold())
  embed.add_field(name="Player", value=player.get("name", "Unknown"), inline=False)
  embed.add_field(name="Balance", value=str(player.get("money", 0)), inline=True)
  embed.description = "Use the buttons below to view Leaderboard, Ascend, or Abilities."
  return embed


class AscensionAbilitiesView(discord.ui.View):
  def __init__(self, player, purchase_handler, panel_message=None):
    super().__init__(timeout=600)
    self.purchase_handler = purchase_handler
    self.panel_message = panel_message

    abilities = _abilities_or_default(player)
    greed_active = bool(abilities.get("greed", False))
    stars = int(player.get("gambler_stars", 0) or 0)
    can_buy = stars >= 1 and not greed_active
    if stars <= 0:
      return

    def _add_button(label, custom_id, row, *, style=discord.ButtonStyle.primary, disabled=False, action=None):
      button = discord.ui.Button(
        label=label,
        style=style,
        custom_id=custom_id,
        row=row,
        disabled=disabled,
      )

      async def _callback(interaction: discord.Interaction):
        await self.purchase_handler(interaction, action=action, panel_message=self.panel_message)

      button.callback = _callback
      self.add_item(button)

    foundation = int(abilities.get("foundation", 0) or 0)
    fickle = int(abilities.get("fickle", 0) or 0)
    influence = int(abilities.get("influence", 0) or 0)
    heavy_die = int(abilities.get("heavy_die", 0) or 0)
    sage = int(abilities.get("sage", 0) or 0)
    passion = int(abilities.get("passion", 0) or 0)
    unbounded = bool(abilities.get("unbounded", False))
    blessed = bool(abilities.get("blessed", False))
    greed = bool(abilities.get("greed", False))

    # One button per ability, showing current/max. Clicking buys the next tier (or toggles for Greed).
    _add_button(
      f"Foundation {foundation}/5",
      "asc_foundation",
      row=0,
      disabled=not (can_buy and foundation < 5),
      action={"type": "advance", "key": "foundation"},
    )
    _add_button(
      f"Fickle {fickle}/2",
      "asc_fickle",
      row=0,
      disabled=not (can_buy and fickle < 2),
      action={"type": "advance", "key": "fickle"},
    )
    _add_button(
      f"Influence {influence}/3",
      "asc_influence",
      row=0,
      disabled=not (can_buy and influence < 3),
      action={"type": "advance", "key": "influence"},
    )
    _add_button(
      f"Heavy Die {heavy_die}/3",
      "asc_heavy_die",
      row=0,
      disabled=not (can_buy and heavy_die < 3),
      action={"type": "advance", "key": "heavy_die"},
    )
    _add_button(
      f"Sage {sage}/3",
      "asc_sage",
      row=0,
      disabled=not (can_buy and sage < 3),
      action={"type": "advance", "key": "sage"},
    )
    _add_button(
      f"Passion {passion}/3",
      "asc_passion",
      row=1,
      disabled=not (can_buy and passion < 3),
      action={"type": "advance", "key": "passion"},
    )

    _add_button(
      f"Unbounded {1 if unbounded else 0}/1",
      "asc_unbounded",
      row=1,
      disabled=not (can_buy and not unbounded),
      action={"type": "advance", "key": "unbounded"},
    )
    _add_button(
      f"Blessed {1 if blessed else 0}/1",
      "asc_blessed",
      row=1,
      disabled=not (can_buy and not blessed),
      action={"type": "advance", "key": "blessed"},
    )
    _add_button(
      f"Greed {1 if greed else 0}/1",
      "asc_greed",
      row=1,
      style=discord.ButtonStyle.danger if not greed else discord.ButtonStyle.secondary,
      disabled=not (stars >= 1),
      action={"type": "toggle", "key": "greed"},
    )


class GambleMenuView(discord.ui.View):
  def __init__(self, player, leaderboard_handler, ascend_handler, ascension_abilities_handler, gamble_handler, panel_message=None):
    super().__init__(timeout=None)
    self.leaderboard_handler = leaderboard_handler
    self.ascend_handler = ascend_handler
    self.ascension_abilities_handler = ascension_abilities_handler
    self.gamble_handler = gamble_handler
    self.panel_message = panel_message

    def _add_button(label, custom_id, row, *, style=discord.ButtonStyle.primary, disabled=False, action=None, callback=None):
      button = discord.ui.Button(
        label=label,
        style=style,
        custom_id=custom_id,
        row=row,
        disabled=disabled,
      )

      async def _callback(interaction: discord.Interaction):
        if callback:
          await callback(interaction)
        else:
          await interaction.response.defer()

      button.callback = _callback
      self.add_item(button)


    _add_button("Gamble", "menu_gamble", row=0, style=discord.ButtonStyle.success, callback=lambda i: self.gamble_handler(i, panel_message=self.panel_message))
    _add_button("Leaderboard", "menu_leaderboard", row=0, callback=lambda i: self.leaderboard_handler(i))
    _add_button("Ascend", "menu_ascend", row=0, callback=lambda i: self.ascend_handler(i, panel_message=self.panel_message))
    _add_button("Abilities", "menu_abilities", row=0, callback=lambda i: self.ascension_abilities_handler(i, panel_message=self.panel_message))


def build_gamble_embed(player, pull_label):
  embed = discord.Embed(title="Catgpt Gamble Game", color=discord.Color.gold())
  embed.add_field(name="Player", value=player["name"], inline=False)
  embed.add_field(name="Balance", value=str(player["money"]), inline=True)
  embed.add_field(name="Win Streak", value=str(player["win_streak"]), inline=True)
  amount_change = player["last_amount_change"]
  amount_text = f"+{amount_change}" if amount_change > 0 else str(amount_change)
  embed.add_field(name="Amount Won This Round", value=amount_text, inline=True)
  embed.add_field(name="Last Multiplier", value=player["last_multiplier"], inline=True)
  next_pull = player.get("next_pull")
  next_pull_revealed = player.get("next_pull_revealed", False)
  next_pull_text = pull_label(next_pull) if next_pull and next_pull_revealed else "Hidden"
  embed.add_field(name="Next Pull", value=next_pull_text, inline=True)
  return embed


class AscendConfirmView(discord.ui.View):
  def __init__(self, confirm_handler, cancel_handler=None, panel_message=None):
    super().__init__(timeout=30)
    self.confirm_handler = confirm_handler
    self.cancel_handler = cancel_handler
    self.panel_message = panel_message

  @discord.ui.button(label="Confirm Ascend", style=discord.ButtonStyle.danger, custom_id="gamble_ascend_confirm")
  async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.confirm_handler(interaction, panel_message=self.panel_message)

  @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="gamble_ascend_cancel")
  async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
    if self.cancel_handler is not None:
      await self.cancel_handler(interaction)
      return
    await interaction.response.edit_message(content="Ascend cancelled.", view=None)


class GambleAmountModal(discord.ui.Modal):
  def __init__(self, amount_submit_handler, source_message=None):
    super().__init__(title="Gamble Amount")
    self.amount_submit_handler = amount_submit_handler
    self.source_message = source_message
    self.amount = discord.ui.TextInput(
      label="Amount to wager",
      placeholder="Enter a number, or type all / half",
      required=True,
      max_length=16
    )
    self.add_item(self.amount)

  async def on_submit(self, interaction: discord.Interaction):
    await self.amount_submit_handler(interaction, str(self.amount.value), self.source_message)


class GambleView(discord.ui.View):
  def __init__(
    self,
    player,
    amount_submit_handler,
    half_handler,
    all_handler,
    leaderboard_handler,
    scry_handler,
    reroll_handler,
    ascend_handler,
    ascension_abilities_handler,
  ):
    super().__init__(timeout=None)
    scry_percent = _format_percent(_scry_cost_percent(player))
    reroll_percent = _format_percent(_reroll_cost_percent(player))

    self.amount_submit_handler = amount_submit_handler
    self.half_handler = half_handler
    self.all_handler = all_handler
    self.leaderboard_handler = leaderboard_handler
    self.scry_handler = scry_handler
    self.reroll_handler = reroll_handler
    self.ascend_handler = ascend_handler
    self.ascension_abilities_handler = ascension_abilities_handler
    # menu_handler should be set by the creator of this view if they want a menu button.
    self.menu_handler = None
    for item in self.children:
      custom_id = getattr(item, "custom_id", None)
      if custom_id == "gamble_peek_next":
        item.label = f"Scry ({scry_percent}%)"
      elif custom_id == "gamble_reroll_next":
        item.label = f"Reroll ({reroll_percent}%)"

  @discord.ui.button(label="Amount", style=discord.ButtonStyle.primary, custom_id="gamble_amount")
  async def gamble_amount(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_modal(
      GambleAmountModal(self.amount_submit_handler, source_message=interaction.message)
    )

  @discord.ui.button(label="Half", style=discord.ButtonStyle.primary, custom_id="gamble_half")
  async def gamble_half(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.half_handler(interaction)

  @discord.ui.button(label="All", style=discord.ButtonStyle.primary, custom_id="gamble_all")
  async def gamble_all(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.all_handler(interaction)

  @discord.ui.button(label="Scry ($30%)", style=discord.ButtonStyle.success, custom_id="gamble_peek_next")
  async def peek_next_pull(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.scry_handler(interaction)

  @discord.ui.button(label="Reroll ($15%)", style=discord.ButtonStyle.success, custom_id="gamble_reroll_next")
  async def reroll_next_pull(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.reroll_handler(interaction)
  

  @discord.ui.button(label="Menu", style=discord.ButtonStyle.secondary, custom_id="gamble_menu")
  async def menu(self, interaction: discord.Interaction, button: discord.ui.Button):
    if self.menu_handler:
      await self.menu_handler(interaction, panel_message=interaction.message)
      return
    # fallback: inform user if no menu handler wired
    await interaction.response.send_message("Menu not available.", ephemeral=True)
