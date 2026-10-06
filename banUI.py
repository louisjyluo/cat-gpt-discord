import discord
from acronym import list_banned_phrases, get_ban_leaderboard
from db import get_contributor_names, upsert_contributor

PAGE_SIZE = 10


def build_ban_list_embed(guild_id, page, entries):
    total = len(entries)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    slice_ = entries[start:start + PAGE_SIZE]

    embed = discord.Embed(title="Banned Phrases", color=discord.Color.red())
    if not slice_:
        embed.description = "No phrases are banned for this server."
    else:
        def _author_tag(author_id):
            return f"<@{author_id}>" if author_id else "*(unclaimed)*"
        lines = [f"**{phrase}** — banned by {_author_tag(author_id)}" for phrase, author_id in slice_]
        embed.description = "\n".join(lines)

    embed.set_footer(text=f"Page {page + 1}/{total_pages} • {total} banned phrase{'s' if total != 1 else ''}")
    return embed


def build_ban_leaderboard_embed(page, rows):
    total = len(rows)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    slice_ = rows[start:start + PAGE_SIZE]

    embed = discord.Embed(title="Ban Leaderboard", color=discord.Color.red())
    if not slice_:
        embed.description = "No one has had a claimed acronym banned yet."
    else:
        lines = [
            f"**#{start + i + 1}** {display_name} — {count} banned phrase{'s' if count != 1 else ''}"
            for i, (author_id, display_name, count) in enumerate(slice_)
        ]
        embed.description = "\n".join(lines)

    embed.set_footer(text=f"Page {page + 1}/{total_pages} • {total} user{'s' if total != 1 else ''}")
    return embed


async def _resolve_leaderboard_names(guild, leaderboard):
    """Attach display names to (author_id, count) pairs, caching lookups per guild."""
    cached_names = get_contributor_names(str(guild.id))
    rows = []
    for author_id, count in leaderboard:
        display_name = cached_names.get(str(author_id))
        if display_name is None:
            member = guild.get_member(int(author_id))
            if member is None:
                try:
                    member = await guild.fetch_member(int(author_id))
                except (discord.NotFound, discord.HTTPException, ValueError):
                    member = None
            display_name = member.display_name if member else f"Unknown user ({author_id})"
            if member:
                upsert_contributor(guild.id, author_id, display_name)
        rows.append((author_id, display_name, count))
    return rows


class BanLeaderboardView(discord.ui.View):
    def __init__(self, guild_id, page, rows):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.rows = rows

        total_pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(page, total_pages - 1))
        self.total_pages = total_pages

        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page - 1
        view = BanLeaderboardView(self.guild_id, new_page, self.rows)
        await interaction.response.edit_message(embed=build_ban_leaderboard_embed(new_page, self.rows), view=view)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page + 1
        view = BanLeaderboardView(self.guild_id, new_page, self.rows)
        await interaction.response.edit_message(embed=build_ban_leaderboard_embed(new_page, self.rows), view=view)

    @discord.ui.button(label="◀ Back to Ban List", style=discord.ButtonStyle.primary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        entries = list_banned_phrases(str(self.guild_id))
        embed = build_ban_list_embed(self.guild_id, 0, entries)
        view = BanListView(self.guild_id, page=0, entries=entries)
        await interaction.response.edit_message(embed=embed, view=view)


class BanListView(discord.ui.View):
    def __init__(self, guild_id, page=0, entries=None):
        super().__init__(timeout=180)
        self.guild_id = guild_id

        if entries is None:
            entries = list_banned_phrases(str(guild_id))
        self.entries = entries

        total_pages = max(1, (len(self.entries) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(page, total_pages - 1))
        self.total_pages = total_pages

        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page - 1
        view = BanListView(self.guild_id, page=new_page, entries=self.entries)
        await interaction.response.edit_message(embed=build_ban_list_embed(self.guild_id, new_page, self.entries), view=view)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.page + 1
        view = BanListView(self.guild_id, page=new_page, entries=self.entries)
        await interaction.response.edit_message(embed=build_ban_list_embed(self.guild_id, new_page, self.entries), view=view)

    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.primary, row=1)
    async def leaderboard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        leaderboard = get_ban_leaderboard(str(self.guild_id))
        rows = await _resolve_leaderboard_names(interaction.guild, leaderboard)
        embed = build_ban_leaderboard_embed(0, rows)
        view = BanLeaderboardView(self.guild_id, page=0, rows=rows)
        await interaction.edit_original_response(embed=embed, view=view)
