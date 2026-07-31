import discord
from dictionary import list_all_acronyms, claim_acronym, unclaim_acronym

PAGE_SIZE = 10


def _filter_by_prefix(entries, prefix):
    """Filter (acronym, phrase, author_id) tuples where the acronym starts with prefix (case-insensitive)."""
    prefix_upper = prefix.strip().upper()
    return [entry for entry in entries if entry[0].startswith(prefix_upper)]


def build_dict_embed(guild_id, page, entries, search_prefix=None):
    total = len(entries)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    slice_ = entries[start:start + PAGE_SIZE]

    title = "Server Acronym Dictionary"
    if search_prefix:
        title += f" — prefix: {search_prefix.upper()}"

    embed = discord.Embed(title=title, color=discord.Color.teal())

    if not slice_:
        embed.description = (
            f"No acronyms found with prefix **{search_prefix.upper()}**."
            if search_prefix
            else "No acronyms stored for this server."
        )
    else:
        def _author_tag(author_id):
            return f"<@{author_id}>" if author_id else "*(unclaimed)*"
        lines = [f"**{acro}** → {phrase} — {_author_tag(author_id)}" for acro, phrase, author_id in slice_]
        embed.description = "\n".join(lines)

    embed.set_footer(text=f"Page {page + 1}/{total_pages} • {total} entr{'y' if total == 1 else 'ies'}")
    return embed


class DictSearchModal(discord.ui.Modal, title="Search by Prefix"):
    prefix_input = discord.ui.TextInput(
        label="Acronym Prefix",
        placeholder="e.g. WTF, GG, BL...",
        max_length=20,
        required=True,
    )

    def __init__(self, guild_id, original_message):
        super().__init__()
        self.guild_id = guild_id
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        prefix = self.prefix_input.value.strip()
        all_entries = list_all_acronyms(str(self.guild_id))
        filtered = _filter_by_prefix(all_entries, prefix)
        embed = build_dict_embed(self.guild_id, 0, filtered, search_prefix=prefix)
        view = DictView(self.guild_id, page=0, entries=filtered, search_prefix=prefix)
        await interaction.response.defer()
        await self.original_message.edit(embed=embed, view=view)


class DictView(discord.ui.View):
    def __init__(self, guild_id, page=0, entries=None, search_prefix=None):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.search_prefix = search_prefix

        if entries is None:
            entries = list_all_acronyms(str(guild_id))
        self.entries = entries

        total_pages = max(1, (len(self.entries) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(page, total_pages - 1))
        self.total_pages = total_pages

        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        self.clear_search_button.disabled = not bool(search_prefix)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page - 1
        embed = build_dict_embed(self.guild_id, new_page, self.entries, self.search_prefix)
        view = DictView(self.guild_id, page=new_page, entries=self.entries, search_prefix=self.search_prefix)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page + 1
        embed = build_dict_embed(self.guild_id, new_page, self.entries, self.search_prefix)
        view = DictView(self.guild_id, page=new_page, entries=self.entries, search_prefix=self.search_prefix)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🔍 Search", style=discord.ButtonStyle.primary, row=0)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DictSearchModal(self.guild_id, interaction.message))

    @discord.ui.button(label="✖ Clear", style=discord.ButtonStyle.danger, row=0)
    async def clear_search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_entries = list_all_acronyms(str(self.guild_id))
        embed = build_dict_embed(self.guild_id, 0, all_entries)
        view = DictView(self.guild_id, page=0, entries=all_entries, search_prefix=None)
        await interaction.response.edit_message(embed=embed, view=view)


class ClaimSelectView(discord.ui.View):
    def __init__(self, guild_id, acronym_str, phrases, target_user_id, claimer_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.acronym_str = acronym_str.upper()
        self.target_user_id = target_user_id
        self.claimer_id = claimer_id

        options = [discord.SelectOption(label=p[:100], value=p[:100]) for p in phrases[:25]]
        select = discord.ui.Select(
            placeholder=f"Which '{self.acronym_str}' phrase?",
            options=options,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.claimer_id:
            await interaction.response.send_message("This isn't your claim prompt.", ephemeral=True)
            return
        phrase = interaction.data['values'][0]
        try:
            claim_acronym(self.guild_id, self.acronym_str, self.target_user_id, phrase=phrase)
            if self.target_user_id == self.claimer_id:
                await interaction.response.edit_message(content=f"✅ Claimed **{self.acronym_str}** → {phrase}.", view=None)
            else:
                await interaction.response.edit_message(content=f"✅ Claimed **{self.acronym_str}** → {phrase} for <@{self.target_user_id}>.", view=None)
        except ValueError as e:
            await interaction.response.edit_message(content=str(e), view=None)


class UnclaimSelectView(discord.ui.View):
    def __init__(self, guild_id, acronym_str, phrases, target_user_id, claimer_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.acronym_str = acronym_str.upper()
        self.target_user_id = target_user_id
        self.claimer_id = claimer_id

        options = [discord.SelectOption(label=p[:100], value=p[:100]) for p in phrases[:25]]
        select = discord.ui.Select(
            placeholder=f"Which '{self.acronym_str}' phrase?",
            options=options,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.claimer_id:
            await interaction.response.send_message("This isn't your unclaim prompt.", ephemeral=True)
            return
        phrase = interaction.data['values'][0]
        try:
            unclaim_acronym(self.guild_id, self.acronym_str, self.target_user_id, phrase=phrase)
            if self.target_user_id == self.claimer_id:
                await interaction.response.edit_message(content=f"✅ **{self.acronym_str}** → {phrase} has been unclaimed.", view=None)
            else:
                await interaction.response.edit_message(content=f"✅ Removed claim on **{self.acronym_str}** → {phrase} from <@{self.target_user_id}>.", view=None)
        except ValueError as e:
            await interaction.response.edit_message(content=str(e), view=None)
