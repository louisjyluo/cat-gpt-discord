import discord

PAGE_SIZE = 8

REGULAR_COMMANDS = [
  "`catgpt <message>`: Ask CatGPT a question.",
  "`catgpt summarize` or `catsum`: Reply to a message to summarize it.",
  "`catsum <number>`: Summarizes the last x messages in the channel (max 50).",
  "`lex <word>`: Alphabetically sorts letters in the word.",
  "`acro <phrase>`: Creates/stores an acronym for a word or phrase.",
  "`unacro <phrase>`: Removes a stored acronym for a word or phrase.",
  "`dict .`: Lists all stored acronyms for this server.",
  "`claim <ACRO>`: Claim authorship of an acronym.",
  "`blame <ACRO>`: Show who owns an acronym.",
  "`unclaim <ACRO>`: Remove your claim on an acronym.",
  "`charades [number]`: Sends that many random acronym phrases (default 3, max 10).",
  "`notif`: Toggles whether this channel gets a ping when I come online.",
  "`i_hate_fun`: Opts you out of acro/dict commands and acronym auto-responses.",
  "`i_love_fun`: Opts you back into acro/dict commands and acronym auto-responses.",
  "`roll`: Rolls a random number from 1 to 1000.",
  "`bank [username]`: Shows your balance or another user's balance.",
  "`racer`: Opens your racers UI (alias of `racers`).",
  "`racers`: Opens your racers UI (create racer + form by index).",
  "`race`: Opens the race panel.",
  "`race history`: Shows last 10 races with details button.",
  "`gamble`: Opens the gambling panel.",
  "`say hi`: Bot says hello.",
  "`cat`: Sends the cat gif.",
  "`blouis`: Sends the Blouis image.",
  "`redward`: Sends the Redward image.",
  "`help`: Shows this command list.",
]

ADMIN_COMMANDS = [
  "`acro *`: Lists all stored acronym phrases.",
  "`unacroall <user>`: Removes every acronym created by that user.",
  "`claim <ACRO> <user>`: Claim an acronym for another user.",
  "`unclaim <ACRO> <user>`: Remove a user's claim on an acronym.",
  "`ban <phrase>`: Bans a phrase from being acro'd.",
  "`unban <phrase>`: Unbans a phrase.",
  "`stim <username> <$amount>`: Adds money to a user's balance.",
]


def build_help_embed(page, admin_mode=False):
  commands = ADMIN_COMMANDS if admin_mode else REGULAR_COMMANDS
  total = len(commands)
  total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
  page = max(0, min(page, total_pages - 1))

  start = page * PAGE_SIZE
  slice_ = commands[start:start + PAGE_SIZE]

  title = "Blouis-only Commands" if admin_mode else "CatGPT Commands"
  embed = discord.Embed(title=title, description="\n".join(f"- {c}" for c in slice_), color=discord.Color.teal())
  embed.set_footer(text=f"Page {page + 1}/{total_pages} • {total} command{'s' if total != 1 else ''}")
  return embed


class HelpView(discord.ui.View):
  def __init__(self, page=0, admin_mode=False):
    super().__init__(timeout=180)
    self.admin_mode = admin_mode
    commands = ADMIN_COMMANDS if admin_mode else REGULAR_COMMANDS
    self.total_pages = max(1, (len(commands) + PAGE_SIZE - 1) // PAGE_SIZE)
    self.page = max(0, min(page, self.total_pages - 1))

    self.prev_button.disabled = self.page == 0
    self.next_button.disabled = self.page >= self.total_pages - 1
    self.admin_button.label = "◀ Back" if admin_mode else "Admin"

  @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
  async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    view = HelpView(page=self.page - 1, admin_mode=self.admin_mode)
    await interaction.response.edit_message(embed=build_help_embed(view.page, self.admin_mode), view=view)

  @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
  async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    view = HelpView(page=self.page + 1, admin_mode=self.admin_mode)
    await interaction.response.edit_message(embed=build_help_embed(view.page, self.admin_mode), view=view)

  @discord.ui.button(label="Admin", style=discord.ButtonStyle.primary, row=0)
  async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    new_admin_mode = not self.admin_mode
    view = HelpView(page=0, admin_mode=new_admin_mode)
    await interaction.response.edit_message(embed=build_help_embed(0, new_admin_mode), view=view)
