import discord
from db import set_llm_model
from llm import MODEL_CHOICES


class LlmModelView(discord.ui.View):
  def __init__(self, guild_id, owner_id, current_key=None):
    super().__init__(timeout=60)
    self.guild_id = guild_id
    self.owner_id = owner_id

    options = [
      discord.SelectOption(label=key.capitalize(), value=key, description=model, default=key == current_key)
      for key, model in MODEL_CHOICES.items()
    ]
    select = discord.ui.Select(placeholder="Choose a model", options=options)
    select.callback = self.on_select
    self.add_item(select)

  async def on_select(self, interaction: discord.Interaction):
    if interaction.user.id != self.owner_id:
      await interaction.response.send_message("This isn't your model menu.", ephemeral=True)
      return
    key = interaction.data['values'][0]
    set_llm_model(self.guild_id, key)
    await interaction.response.edit_message(
      content=f"🤖 This server now uses **{key.capitalize()}** (`{MODEL_CHOICES[key]}`).",
      view=None,
    )
