"""Sending CatGPT's answers to Discord and reading them back as chat history.

Long text answers and older math replies can span several Discord messages, each replying to the previous
one. The history side regroups them into a single turn.
"""
import asyncio
import io

import discord

from md_render import render_for_discord, split_message
from proof_render import PROOF_FILENAME, needs_proof_source, proof_alt_text, read_proof_source, render_proof_png


async def send_reply(msg, text, can_attach=True):
  """Reply with one proof image when possible, or with Discord Markdown."""
  if can_attach:
    png = await asyncio.to_thread(render_proof_png, text)
    if png:
      try:
        file = discord.File(io.BytesIO(png), filename=PROOF_FILENAME, description=proof_alt_text(text))
        await msg.reply(files=[file], mention_author=True)
        return
      except discord.HTTPException as exc:
        if exc.status not in (403, 413) and exc.code != 40005:
          raise

  sent = msg
  for chunk in split_message(render_for_discord(text or "") or "Mrow?"):
    sent = await sent.reply(mention_author=sent is msg, content=chunk, suppress_embeds=True)


async def _full_proof_text(message):
  for attachment in message.attachments:
    if attachment.filename == PROOF_FILENAME and needs_proof_source(attachment.description):
      try:
        png = await attachment.read()
        return await asyncio.to_thread(read_proof_source, png)
      except (discord.HTTPException, OSError, ValueError):
        return None


async def collect_reply_chain(parent, bot_id, resolve, max_turns, max_messages=30):
  """Walks up the reply chain from `parent`, oldest first, keeping up to `max_turns` turns.

  Consecutive bot messages are fragments of one answer and count as a single turn, so a multipart answer
  can't push the user's question out of the history. `max_messages` bounds the fetches.
  """
  chain = []
  seen = set()
  turns = 0
  prev_is_bot = False
  current = parent
  while current is not None and current.id not in seen and len(chain) < max_messages:
    is_bot = current.author.id == bot_id
    if not (is_bot and prev_is_bot):
      if turns == max_turns:
        break
      turns += 1
    seen.add(current.id)
    chain.append(current)
    prev_is_bot = is_bot
    current = await resolve(current)
  chain.reverse()
  return chain


async def chain_to_history(chain, bot_id, describe):
  """Converts a reply chain into chat history, merging the fragments of each bot answer into one assistant turn."""
  history = []
  prev_is_bot = False
  for m in chain:
    is_bot = m.author.id == bot_id
    text = (await _full_proof_text(m) if is_bot else None) or describe(m)
    if text:
      if is_bot and prev_is_bot and history and history[-1]["role"] == "assistant":
        history[-1]["content"] += f"\n{text}"
      elif is_bot:
        history.append({"role": "assistant", "content": text})
      else:
        history.append({"role": "user", "content": f"{m.author.display_name}: {text}"})
    prev_is_bot = is_bot
  return history
