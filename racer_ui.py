import discord

from db import get_user_balance
from race import MAX_TOTAL_STATS, RACER_COST_PER_OWNED, create_racer, get_race, increase_racer_stat, is_primary_racer, remove_racer_by_index, set_primary_racer


def get_racer_for_owner(guild_id, owner_id, racer_name):
  race = get_race(guild_id)
  return race.find_racer(owner_id=owner_id, racer_name=racer_name)


def get_racer_for_owner_by_index(guild_id, owner_id, racer_index):
  racers = get_racers_for_owner(guild_id, owner_id)
  if not isinstance(racer_index, int) or racer_index < 1 or racer_index > len(racers):
    raise ValueError("Invalid racer index.")
  return racers[racer_index - 1]


def get_racers_for_owner(guild_id, owner_id):
  race = get_race(guild_id)
  return [racer for racer in race.racers if racer.owner_id == owner_id]


def resolve_racer_name(raw_name, guild):
  clean_name = str(raw_name).strip()
  if not clean_name.startswith(":"):
    return clean_name
  if guild is None:
    return clean_name

  # Accept forms like :cat:, :cat, or cat: by trimming leading/trailing colons.
  emoji_name = clean_name.strip(":").strip()
  if not emoji_name:
    return clean_name

  guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
  if guild_emoji is None:
    return clean_name
  return str(guild_emoji)


def build_racers_embed(guild_id, owner_id, owner_name=None):
  racers = get_racers_for_owner(guild_id, owner_id)
  balance = get_user_balance(owner_id)
  display_name = owner_name or f"<@{owner_id}>"
  embed = discord.Embed(title="Your Racers", color=discord.Color.teal())
  embed.add_field(name="Owner", value=display_name, inline=True)
  embed.add_field(name="Balance", value=f"${balance}", inline=True)

  if not racers:
    embed.add_field(name="Racers", value="You don't have any racers yet.", inline=False)
    embed.add_field(name="How to Start", value="Use Create Racer to make your first racer.", inline=False)
    return embed

  lines = []
  for index, racer in enumerate(racers, start=1):
    points_left = MAX_TOTAL_STATS - racer.stats_total()
    primary_tag = " [PRIMARY]" if is_primary_racer(guild_id, owner_id, racer.name) else ""
    lines.append(
      f"{index}. {racer.name}{primary_tag}: spd {racer.speed}/5, sta {racer.stamina}/5, cha {racer.charisma}/5, adr {racer.adrenaline}/5, points left {points_left}"
    )

  racers_text = "\n".join(lines)
  if len(racers_text) > 1024:
    racers_text = racers_text[:1021] + "..."
  embed.add_field(name="Racers", value=racers_text, inline=False)
  return embed


def build_racer_embed(guild_id, owner_id, racer_name, owner_name=None):
  racer = get_racer_for_owner(guild_id, owner_id, racer_name)
  remaining_points = MAX_TOTAL_STATS - racer.stats_total()
  primary_text = "Yes" if is_primary_racer(guild_id, owner_id, racer.name) else "No"
  balance = get_user_balance(owner_id)
  display_name = owner_name or f"<@{owner_id}>"

  embed = discord.Embed(title="Racer UI", color=discord.Color.green())
  embed.add_field(name="Owner", value=display_name, inline=True)
  embed.add_field(name="Balance", value=f"${balance}", inline=True)
  embed.add_field(name="Name", value=racer.name, inline=False)
  embed.add_field(name="Primary", value=primary_text, inline=True)
  embed.add_field(name="Speed", value=str(racer.speed) + "/5", inline=True)
  embed.add_field(name="Stamina", value=str(racer.stamina) + "/5", inline=True)
  embed.add_field(name="Charisma", value=str(racer.charisma) + "/5", inline=True)
  embed.add_field(name="Adrenaline", value=str(racer.adrenaline) + "/5", inline=True)
  embed.add_field(name="Skill Points Remaining", value=str(remaining_points), inline=False)
  return embed


class RacerStatView(discord.ui.View):
  def __init__(self, guild_id, owner_id, racer_name):
    super().__init__(timeout=600)
    self.guild_id = guild_id
    self.owner_id = owner_id
    self.racer_name = racer_name

  async def _upgrade_stat(self, interaction: discord.Interaction, stat_name: str):
    if interaction.user.id != self.owner_id:
      await interaction.response.send_message("Only the owner can modify this racer.", ephemeral=True)
      return

    try:
      increase_racer_stat(self.guild_id, self.owner_id, self.racer_name, stat_name, 1)
      embed = build_racer_embed(self.guild_id, self.owner_id, self.racer_name, interaction.user.display_name)
      await interaction.response.edit_message(embed=embed, view=self)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not upgrade stat: {exc}", ephemeral=True)

  @discord.ui.button(label="Set Primary", style=discord.ButtonStyle.success)
  async def set_primary_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.user.id != self.owner_id:
      await interaction.response.send_message("Only the owner can modify this racer.", ephemeral=True)
      return

    try:
      set_primary_racer(self.guild_id, self.owner_id, self.racer_name)
      embed = build_racer_embed(self.guild_id, self.owner_id, self.racer_name, interaction.user.display_name)
      await interaction.response.edit_message(embed=embed, view=self)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not set primary racer: {exc}", ephemeral=True)

  @discord.ui.button(label="Speed +1", style=discord.ButtonStyle.primary)
  async def speed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self._upgrade_stat(interaction, "speed")

  @discord.ui.button(label="Stamina +1", style=discord.ButtonStyle.primary)
  async def stamina_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self._upgrade_stat(interaction, "stamina")

  @discord.ui.button(label="Charisma +1", style=discord.ButtonStyle.primary)
  async def charisma_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self._upgrade_stat(interaction, "charisma")

  @discord.ui.button(label="Adrenaline +1", style=discord.ButtonStyle.primary)
  async def adrenaline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self._upgrade_stat(interaction, "adrenaline")


class CreateRacerModal(discord.ui.Modal):
  def __init__(self, source_message=None):
    super().__init__(title="Create Racer")
    self.source_message = source_message
    self.racer_name = discord.ui.TextInput(
      label="Racer name",
      placeholder="Enter a unique racer name",
      required=True,
      max_length=32,
    )
    self.add_item(self.racer_name)

  async def on_submit(self, interaction: discord.Interaction):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    try:
      parsed_name = resolve_racer_name(self.racer_name.value, interaction.guild)
      racer = create_racer(interaction.guild_id, interaction.user.id, parsed_name)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not create racer: {exc}", ephemeral=True)
      return

    racers_embed = build_racers_embed(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    if self.source_message is not None:
      await self.source_message.edit(embed=racers_embed, view=RacersPanelView())

    stats_embed = build_racer_embed(interaction.guild_id, interaction.user.id, racer.name, interaction.user.display_name)
    stats_view = RacerStatView(interaction.guild_id, interaction.user.id, racer.name)
    await interaction.response.send_message(f"Created racer {racer.name}.", ephemeral=True)
    await interaction.followup.send(embed=stats_embed, view=stats_view, ephemeral=True)


class RacerFormModal(discord.ui.Modal):
  def __init__(self):
    super().__init__(title="Racer Form")
    self.racer_index = discord.ui.TextInput(
      label="Racer index",
      placeholder="Enter racer index from Your Racers list",
      required=True,
      max_length=4,
    )
    self.add_item(self.racer_index)

  async def on_submit(self, interaction: discord.Interaction):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    try:
      racer_index = int(str(self.racer_index.value).strip())
      racer = get_racer_for_owner_by_index(interaction.guild_id, interaction.user.id, racer_index)
      embed = build_racer_embed(interaction.guild_id, interaction.user.id, racer.name, interaction.user.display_name)
      view = RacerStatView(interaction.guild_id, interaction.user.id, racer.name)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not open racer form: {exc}", ephemeral=True)
      return
    except Exception:
      await interaction.response.send_message("Could not open racer form: racer index must be an integer.", ephemeral=True)
      return

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RemoveRacerModal(discord.ui.Modal):
  def __init__(self, source_message=None):
    super().__init__(title="Remove Racer")
    self.source_message = source_message
    self.racer_index = discord.ui.TextInput(
      label="Racer index",
      placeholder="Enter racer index from Your Racers list",
      required=True,
      max_length=4,
    )
    self.add_item(self.racer_index)

  async def on_submit(self, interaction: discord.Interaction):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    try:
      racer_index = int(str(self.racer_index.value).strip())
      removed_racer, refund = remove_racer_by_index(interaction.guild_id, interaction.user.id, racer_index)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not remove racer: {exc}", ephemeral=True)
      return
    except Exception:
      await interaction.response.send_message("Could not remove racer: racer index must be an integer.", ephemeral=True)
      return

    racers_embed = build_racers_embed(interaction.guild_id, interaction.user.id, interaction.user.display_name)
    if self.source_message is not None:
      await self.source_message.edit(embed=racers_embed, view=RacersPanelView())

    await interaction.response.send_message(
      f"Removed racer {removed_racer.name}. Refunded ${refund}.",
      ephemeral=True,
    )


class RacersPanelView(discord.ui.View):
  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(label=f"Create Racer (Cost: owned x ${RACER_COST_PER_OWNED})", style=discord.ButtonStyle.primary, custom_id="racers_create")
  async def create_racer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    await interaction.response.send_modal(CreateRacerModal(source_message=interaction.message))

  @discord.ui.button(label="Get Racer (By Index)", style=discord.ButtonStyle.primary, custom_id="racers_form")
  async def form_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    await interaction.response.send_modal(RacerFormModal())

  @discord.ui.button(label="Remove Racer (Refund 50%)", style=discord.ButtonStyle.danger, custom_id="racers_remove")
  async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This racers UI only works in a server.", ephemeral=True)
      return

    await interaction.response.send_modal(RemoveRacerModal(source_message=interaction.message))