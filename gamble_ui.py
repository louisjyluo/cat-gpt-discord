import discord


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
    amount_submit_handler,
    half_handler,
    all_handler,
    leaderboard_handler,
    pool_left_handler,
    scry_handler,
    reroll_handler,
    show_pool_left=True,
  ):
    super().__init__(timeout=None)
    self.amount_submit_handler = amount_submit_handler
    self.half_handler = half_handler
    self.all_handler = all_handler
    self.leaderboard_handler = leaderboard_handler
    self.pool_left_handler = pool_left_handler
    self.scry_handler = scry_handler
    self.reroll_handler = reroll_handler
    if not show_pool_left:
      for item in list(self.children):
        if getattr(item, "custom_id", None) == "gamble_pool_left":
          self.remove_item(item)

  @discord.ui.button(label="Gamble Amount", style=discord.ButtonStyle.primary, custom_id="gamble_amount")
  async def gamble_amount(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_modal(
      GambleAmountModal(self.amount_submit_handler, source_message=interaction.message)
    )

  @discord.ui.button(label="Gamble Half", style=discord.ButtonStyle.primary, custom_id="gamble_half")
  async def gamble_half(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.half_handler(interaction)

  @discord.ui.button(label="Gamble All", style=discord.ButtonStyle.primary, custom_id="gamble_all")
  async def gamble_all(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.all_handler(interaction)

  @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.danger, custom_id="gamble_leaderboard")
  async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.leaderboard_handler(interaction)

  @discord.ui.button(label="Pool Left", style=discord.ButtonStyle.primary, custom_id="gamble_pool_left")
  async def pool_left(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.pool_left_handler(interaction)

  @discord.ui.button(label="Scry ($30%)", style=discord.ButtonStyle.success, custom_id="gamble_peek_next")
  async def peek_next_pull(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.scry_handler(interaction)

  @discord.ui.button(label="Reroll ($15%)", style=discord.ButtonStyle.success, custom_id="gamble_reroll_next")
  async def reroll_next_pull(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.reroll_handler(interaction)
