import asyncio
import discord

from db import get_recent_race_history
from race import JOIN_RACE_COST, advance_race, consume_pending_finish_response, get_race, get_race_message, join_primary_racer, place_race_bet, start_new_race


AUTO_ADVANCE_INTERVAL_SECONDS = 2.0
_auto_race_tasks = {}


def _is_auto_race_running(guild_id: int) -> bool:
  task = _auto_race_tasks.get(guild_id)
  return task is not None and not task.done()


def _stop_auto_race_task(guild_id: int):
  task = _auto_race_tasks.pop(guild_id, None)
  if task is not None and not task.done():
    task.cancel()


def build_race_embed(guild_id):
  race = get_race(guild_id)
  embed = discord.Embed(title="Race UI", color=discord.Color.blurple())
  embed.add_field(name="Status", value=get_race_message(guild_id), inline=False)
  embed.add_field(name="Turn", value=str(race.turns), inline=True)

  if race.racers:
    summary_lines = race.summary_lines()
    track_lines = race.track_lines()
    summary_text = "\n".join(summary_lines)
    track_text = "\n".join(track_lines)

    if len(summary_text) > 1024:
      summary_text = summary_text[:1021] + "..."
    if len(track_text) > 1024:
      track_text = track_text[:1021] + "..."

    embed.add_field(name="Racer List", value=summary_text, inline=False)
    embed.add_field(name="Track", value=track_text, inline=False)
  else:
    embed.add_field(name="Racer List", value="No racers yet.", inline=False)
    embed.add_field(name="Track", value="No racers yet.", inline=False)

  return embed


def build_race_history_box(guild_id, limit=10):
  history = get_recent_race_history(guild_id, limit)
  if not history:
    return "No race history yet."

  lines = ["Recent Race History"]
  for index, record in enumerate(history, start=1):
    turns = int(record.get("turns", 0))
    results = record.get("results", []) if isinstance(record.get("results", []), list) else []
    winner = "N/A"
    for row in results:
      if isinstance(row, dict) and row.get("rank") == 1:
        winner = str(row.get("name", "N/A"))
        break
    lines.append(f"{index}. turns={turns} winner={winner}")

  return "\n".join(lines)


def build_race_history_embed(guild_id, limit=10):
  embed = discord.Embed(title="Race History", color=discord.Color.blurple())
  history = get_recent_race_history(guild_id, limit)
  if not history:
    embed.description = "No race history yet."
    return embed

  for index, record in enumerate(history, start=1):
    turns = int(record.get("turns", 0))
    results = record.get("results", []) if isinstance(record.get("results", []), list) else []
    winner = "N/A"
    for row in results:
      if isinstance(row, dict) and row.get("rank") == 1:
        winner = str(row.get("name", "N/A"))
        break

    embed.add_field(
      name=f"Race {index}",
      value=f"Turns: {turns}\nWinner: {winner}",
      inline=False,
    )
  return embed


def build_race_history_detail_embed(guild_id, history_index, limit=10):
  history = get_recent_race_history(guild_id, limit)
  if not isinstance(history_index, int) or history_index < 1 or history_index > len(history):
    raise ValueError("Invalid race index.")

  record = history[history_index - 1]
  turns = int(record.get("turns", 0))
  results = record.get("results", []) if isinstance(record.get("results", []), list) else []

  embed = discord.Embed(title=f"Race {history_index} Details", color=discord.Color.blurple())
  embed.add_field(name="Turns", value=str(turns), inline=False)

  lines = []
  for row in results:
    if not isinstance(row, dict):
      continue
    rank = row.get("rank")
    name = row.get("name", "Unknown")
    owner_id = row.get("owner_id", "?")
    position = row.get("position", 0)
    if rank == "DNF":
      lines.append(f"DNF - {name} (<@{owner_id}>) - {position}/24")
    else:
      rank_prefix = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
      lines.append(f"{rank_prefix} {name} (<@{owner_id}>)")

  if not lines:
    lines.append("No results recorded.")

  standings_text = "\n".join(lines)
  if len(standings_text) > 1024:
    standings_text = standings_text[:1021] + "..."
  embed.add_field(name="Standings", value=standings_text, inline=False)
  return embed


class RaceHistorySelect(discord.ui.Select):
  def __init__(self, guild_id, limit=10):
    self.guild_id = guild_id
    self.limit = limit
    history = get_recent_race_history(guild_id, limit)

    options = []
    for index, record in enumerate(history, start=1):
      turns = int(record.get("turns", 0))
      results = record.get("results", []) if isinstance(record.get("results", []), list) else []
      winner = "N/A"
      for row in results:
        if isinstance(row, dict) and row.get("rank") == 1:
          winner = str(row.get("name", "N/A"))
          break

      winner_display = winner if len(winner) <= 65 else winner[:62] + "..."
      options.append(
        discord.SelectOption(
          label=f"Race {index}",
          description=f"Winner: {winner_display} | Turns: {turns}",
          value=str(index),
        )
      )

    if not options:
      options = [discord.SelectOption(label="No races yet", description="Run a race first.", value="0")]

    super().__init__(
      placeholder="Select a race to view details",
      min_values=1,
      max_values=1,
      options=options,
      disabled=len(history) == 0,
    )

  async def callback(self, interaction: discord.Interaction):
    selected = self.values[0]
    if selected == "0":
      await interaction.response.send_message("No races available yet.", ephemeral=True)
      return

    try:
      race_index = int(selected)
      embed = build_race_history_detail_embed(self.guild_id, race_index, self.limit)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not fetch race details: {exc}", ephemeral=True)
      return

    await interaction.response.send_message(embed=embed, ephemeral=True)


class RaceHistoryView(discord.ui.View):
  def __init__(self, guild_id, limit=10):
    super().__init__(timeout=600)
    self.guild_id = guild_id
    self.limit = limit
    self.add_item(RaceHistorySelect(guild_id, limit))

  @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
  async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race history UI only works in a server.", ephemeral=True)
      return
    await interaction.response.edit_message(
      embed=build_race_history_embed(self.guild_id, self.limit),
      view=RaceHistoryView(self.guild_id, self.limit),
    )


class RacePanelView(discord.ui.View):
  def __init__(self, guild_id=None):
    super().__init__(timeout=None)
    if guild_id is not None:
      race = get_race(guild_id)
      self.new_race_button.disabled = not race.is_over()
      self.start_race_button.label = "Race Running" if _is_auto_race_running(guild_id) else "Start Race"

  async def _refresh_message(self, interaction: discord.Interaction):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    embed = build_race_embed(interaction.guild_id)
    await interaction.response.edit_message(embed=embed, view=RacePanelView(interaction.guild_id))

  async def _run_auto_race_loop(self, interaction: discord.Interaction):
    guild_id = interaction.guild_id
    message = interaction.message
    channel = interaction.channel
    if guild_id is None or message is None or channel is None:
      return

    try:
      while _is_auto_race_running(guild_id):
        race = advance_race(guild_id)
        await message.edit(embed=build_race_embed(guild_id), view=RacePanelView(guild_id))

        finish_text = consume_pending_finish_response(guild_id)
        if finish_text:
          await channel.send(finish_text)

        if race.is_over():
          break

        await asyncio.sleep(AUTO_ADVANCE_INTERVAL_SECONDS)
    except asyncio.CancelledError:
      # Task was intentionally stopped by user interaction.
      raise
    finally:
      _auto_race_tasks.pop(guild_id, None)
      try:
        await message.edit(embed=build_race_embed(guild_id), view=RacePanelView(guild_id))
      except Exception:
        pass

  @discord.ui.button(label="Start Race", style=discord.ButtonStyle.success, custom_id="race_start")
  async def start_race_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    if _is_auto_race_running(interaction.guild_id):
      await interaction.response.send_message("Race is already running.", ephemeral=True)
      return

    race = get_race(interaction.guild_id)
    if not race.joined_racers():
      await interaction.response.send_message("No racers have joined this race yet.", ephemeral=True)
      return

    if race.is_over():
      await interaction.response.send_message("Race is already finished. Start a new race first.", ephemeral=True)
      return

    task = asyncio.create_task(self._run_auto_race_loop(interaction))
    _auto_race_tasks[interaction.guild_id] = task
    await interaction.response.edit_message(
      embed=build_race_embed(interaction.guild_id),
      view=RacePanelView(interaction.guild_id),
    )

  @discord.ui.button(label=f"Join Race (${JOIN_RACE_COST})", style=discord.ButtonStyle.primary, custom_id="race_join")
  async def join_race_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    try:
      racer = join_primary_racer(interaction.guild_id, interaction.user.id)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not join race: {exc}", ephemeral=True)
      return

    embed = build_race_embed(interaction.guild_id)
    await interaction.response.edit_message(embed=embed, view=RacePanelView(interaction.guild_id))

  @discord.ui.button(label="Bet", style=discord.ButtonStyle.secondary, custom_id="race_bet")
  async def bet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    await interaction.response.send_modal(RaceBetModal())

  @discord.ui.button(label="New Race", style=discord.ButtonStyle.danger, custom_id="race_new", row=1)
  async def new_race_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    try:
      _stop_auto_race_task(interaction.guild_id)
      start_new_race(interaction.guild_id)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not start new race: {exc}", ephemeral=True)
      return

    embed = build_race_embed(interaction.guild_id)
    await interaction.response.edit_message(embed=embed, view=RacePanelView(interaction.guild_id))


class RaceBetModal(discord.ui.Modal):
  def __init__(self):
    super().__init__(title="Place Race Bet")
    self.racer_index = discord.ui.TextInput(
      label="Racer Index",
      placeholder="Use index from Racer List (1, 2, 3, ...)",
      required=True,
      max_length=4,
    )
    self.wager = discord.ui.TextInput(
      label="Wager Amount",
      placeholder="Enter integer wager",
      required=True,
      max_length=12,
    )
    self.add_item(self.racer_index)
    self.add_item(self.wager)

  async def on_submit(self, interaction: discord.Interaction):
    if interaction.guild_id is None:
      await interaction.response.send_message("This race UI only works in a server.", ephemeral=True)
      return

    try:
      racer_index = int(str(self.racer_index.value).strip())
      wager = int(str(self.wager.value).strip())
    except ValueError:
      await interaction.response.send_message("Racer index and wager must be integers.", ephemeral=True)
      return

    try:
      place_race_bet(interaction.guild_id, interaction.user.id, racer_index, wager)
    except ValueError as exc:
      await interaction.response.send_message(f"Could not place bet: {exc}", ephemeral=True)
      return

    await interaction.response.send_message(
      f"Bet placed: racer index {racer_index}, wager {wager}.",
      ephemeral=True,
    )
