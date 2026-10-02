import discord
from datetime import timedelta, timezone
from db import list_pending_acro_votes, get_acro_vote_by_id, delete_acro_vote_by_id, add_check_vote, add_ban_vote
from acronym import finalize_acronym, ban_phrase

BAN_THRESHOLD = 7
PAGE_SIZE = 5


def _paginate(votes, page):
  total_pages = max(1, (len(votes) + PAGE_SIZE - 1) // PAGE_SIZE)
  page = max(0, min(page, total_pages - 1))
  start = page * PAGE_SIZE
  return votes[start:start + PAGE_SIZE], page, total_pages


def build_votes_embed(guild_id, votes, page=0):
  embed = discord.Embed(title="📋 Active Acro Votes", color=discord.Color.gold())

  if not votes:
    embed.description = (
      "🚫 **Ban threshold:** more than 6 ❌ votes bans a phrase instantly.\n\n"
      "No active votes right now. Start one with `acro <phrase>`."
    )
    return embed

  slice_, page, total_pages = _paginate(votes, page)
  lines = []
  for offset, vote in enumerate(slice_):
    idx = page * PAGE_SIZE + offset + 1
    expiry_dt = vote['created_at'] + timedelta(hours=24)
    expiry_unix = int(expiry_dt.replace(tzinfo=timezone.utc).timestamp())
    check_count = len(vote.get('check_voters', []))
    ban_count = len(vote.get('ban_voters', []))
    lines.append(
      f"**{idx}.** **{vote['phrase']}** → **{vote['acronym']}**\n"
      f"✅ {check_count}/{vote['threshold']} to pass • ❌ {ban_count}/{BAN_THRESHOLD} to ban • ⏳ expires <t:{expiry_unix}:R>"
    )

  embed.description = (
    "🚫 **Ban threshold:** more than 6 ❌ votes bans a phrase instantly.\n\n"
    + "\n\n".join(lines)
  )
  embed.set_footer(text=f"Page {page + 1}/{total_pages} • {len(votes)} active vote{'s' if len(votes) != 1 else ''}")
  return embed


class AcroVoteIndexModal(discord.ui.Modal):
  index_input = discord.ui.TextInput(label="Vote #", placeholder="e.g. 1", max_length=3, required=True)

  def __init__(self, guild_id, votes, action, page, original_message):
    title_map = {"vote": "Vote to Approve", "ban": "Vote to Ban", "stop": "Stop a Vote"}
    super().__init__(title=title_map[action])
    self.guild_id = guild_id
    self.votes = votes
    self.action = action
    self.page = page
    self.original_message = original_message

  async def on_submit(self, interaction: discord.Interaction):
    raw = self.index_input.value.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(self.votes)):
      await interaction.response.send_message(f"Enter a number between 1 and {len(self.votes)}.", ephemeral=True)
      return

    selected = self.votes[int(raw) - 1]
    vote = get_acro_vote_by_id(selected['_id'])
    if vote is None:
      await interaction.response.send_message("That vote has already been resolved or expired.", ephemeral=True)
      return

    if self.action == "vote":
      vote = add_check_vote(vote['_id'], interaction.user.id)
      if len(vote['check_voters']) >= vote['threshold']:
        delete_acro_vote_by_id(vote['_id'])
        finalize_acronym(vote['guild_id'], vote['phrase'], vote['acronym'], vote.get('author_id'))
        await interaction.response.send_message(f"✅ **{vote['phrase']}** passed and was added as **{vote['acronym']}**!")
      else:
        await interaction.response.send_message(
          f"Voted ✅ for **{vote['phrase']}** ({len(vote['check_voters'])}/{vote['threshold']}).", ephemeral=True
        )
    elif self.action == "ban":
      vote = add_ban_vote(vote['_id'], interaction.user.id)
      if len(vote['ban_voters']) > 6:
        delete_acro_vote_by_id(vote['_id'])
        ban_phrase(vote['guild_id'], vote['phrase'])
        await interaction.response.send_message(f"🚫 **{vote['phrase']}** was banned.")
      else:
        await interaction.response.send_message(
          f"Voted ❌ for **{vote['phrase']}** ({len(vote['ban_voters'])}/{BAN_THRESHOLD}).", ephemeral=True
        )
    else:
      delete_acro_vote_by_id(vote['_id'])
      await interaction.response.send_message(f"🛑 Stopped the vote for **{vote['phrase']}**.", ephemeral=True)

    if self.original_message is not None:
      refreshed = list_pending_acro_votes(self.guild_id)
      try:
        await self.original_message.edit(
          embed=build_votes_embed(self.guild_id, refreshed, self.page),
          view=VotesPanelView(self.guild_id, self.blouis_id, page=self.page, vote_count=len(refreshed)),
        )
      except discord.HTTPException:
        pass


class VotesPanelView(discord.ui.View):
  def __init__(self, guild_id, blouis_id, page=0, vote_count=None):
    super().__init__(timeout=600)
    self.guild_id = guild_id
    self.blouis_id = blouis_id
    if vote_count is None:
      vote_count = len(list_pending_acro_votes(guild_id))
    total_pages = max(1, (vote_count + PAGE_SIZE - 1) // PAGE_SIZE)
    self.page = max(0, min(page, total_pages - 1))
    self.total_pages = total_pages
    self.prev_button.disabled = self.page <= 0
    self.next_button.disabled = self.page >= self.total_pages - 1

  @discord.ui.button(label="Vote", style=discord.ButtonStyle.success, row=0)
  async def vote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    votes = list_pending_acro_votes(self.guild_id)
    if not votes:
      await interaction.response.send_message("No active votes.", ephemeral=True)
      return
    modal = AcroVoteIndexModal(self.guild_id, votes, "vote", self.page, interaction.message)
    modal.blouis_id = self.blouis_id
    await interaction.response.send_modal(modal)

  @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, row=0)
  async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    votes = list_pending_acro_votes(self.guild_id)
    if not votes:
      await interaction.response.send_message("No active votes.", ephemeral=True)
      return
    modal = AcroVoteIndexModal(self.guild_id, votes, "ban", self.page, interaction.message)
    modal.blouis_id = self.blouis_id
    await interaction.response.send_modal(modal)

  @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary, row=0)
  async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    if interaction.user.id != self.blouis_id:
      await interaction.response.send_message("Only Blouis can stop a vote.", ephemeral=True)
      return
    votes = list_pending_acro_votes(self.guild_id)
    if not votes:
      await interaction.response.send_message("No active votes.", ephemeral=True)
      return
    modal = AcroVoteIndexModal(self.guild_id, votes, "stop", self.page, interaction.message)
    modal.blouis_id = self.blouis_id
    await interaction.response.send_modal(modal)

  @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=1)
  async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    votes = list_pending_acro_votes(self.guild_id)
    new_page = self.page - 1
    embed = build_votes_embed(self.guild_id, votes, new_page)
    view = VotesPanelView(self.guild_id, self.blouis_id, page=new_page, vote_count=len(votes))
    await interaction.response.edit_message(embed=embed, view=view)

  @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
  async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    votes = list_pending_acro_votes(self.guild_id)
    new_page = self.page + 1
    embed = build_votes_embed(self.guild_id, votes, new_page)
    view = VotesPanelView(self.guild_id, self.blouis_id, page=new_page, vote_count=len(votes))
    await interaction.response.edit_message(embed=embed, view=view)
