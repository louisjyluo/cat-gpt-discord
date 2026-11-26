import itertools
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import discord
from PIL import Image

import llm_reply

BOT_ID = 1
_ids = itertools.count(100)


class FakeMessage:
  def __init__(self, author_id, content="", parent=None, name="Tom", sent=None, deny_files=False):
    self.id = next(_ids)
    self.author = SimpleNamespace(id=author_id, display_name=name)
    self.content = content
    self.parent = parent
    self.attachments = []
    self.sent = sent if sent is not None else []
    self.deny_files = deny_files

  async def reply(self, content="", files=None, mention_author=True, suppress_embeds=False):
    if files and self.deny_files:
      raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Permissions")
    m = FakeMessage(BOT_ID, content, parent=self, sent=self.sent, deny_files=self.deny_files)
    for file in files or []:
      async def read(data=file.fp.getvalue()):
        return data
      m.attachments.append(SimpleNamespace(filename=file.filename, description=file.description, read=read))
    m.suppress_embeds = suppress_embeds
    self.sent.append(m)
    return m


async def resolve(m):
  return m.parent


def describe(m):
  return m.content or "\n".join(a.description for a in m.attachments)


class SendReplyTests(unittest.IsolatedAsyncioTestCase):
  async def send(self, text, **kwargs):
    question = FakeMessage(2, "catgpt math pls", **kwargs)
    await llm_reply.send_reply(question, text)
    return question

  async def test_sends_the_entire_proof_as_one_image(self):
    text = "## Proof\n\nTake \\(n = 1\\).\n$$a = b$$\nThen\n$$b = c$$\nHence \\(a = c\\)."
    question = await self.send(text)
    answer, = question.sent
    file, = answer.attachments
    self.assertIs(answer.parent, question)
    self.assertEqual(answer.content, "")
    self.assertEqual(file.filename, "proof.png")
    self.assertEqual(file.description, text)
    with Image.open(BytesIO(await file.read())) as image:
      self.assertEqual(image.format, "PNG")
      self.assertGreater(image.height, 300)

  async def test_bare_url_answer_suppresses_preview(self):
    question = await self.send("https://example.com")
    answer, = question.sent
    self.assertEqual(answer.content, "https://example.com")
    self.assertTrue(answer.suppress_embeds)

  async def test_denied_attachments_fall_back_to_one_text_reply(self):
    question = await self.send("Area:\n$$\\pi r^2$$\nmeow\n$$x^2$$\nend", deny_files=True)
    answer, = question.sent
    self.assertEqual(answer.content, "Area:\n```\n\\pi r^2\n```\nmeow\n```\nx^2\n```\nend")
    self.assertFalse(answer.attachments)

  async def test_render_error_keeps_the_entire_reply_in_text(self):
    question = await self.send("Start.\n$$a=b$$\nThen $$\\frac{$$\nEnd.")
    answer, = question.sent
    self.assertEqual(answer.content, "Start.\n```\na=b\n```\nThen\n```\n\\frac{\n```\nEnd.")
    self.assertFalse(answer.attachments)

  async def test_no_attach_permission_skips_rendering(self):
    question = FakeMessage(2, "catgpt math pls")
    with patch.object(llm_reply, "render_proof_png") as render:
      await llm_reply.send_reply(question, "Area: $$\\pi r^2$$ meow", can_attach=False)
      render.assert_not_called()
    self.assertEqual([m.content for m in question.sent], ["Area:\n```\n\\pi r^2\n```\nmeow"])


class ReplyChainTests(unittest.IsolatedAsyncioTestCase):
  async def test_follow_up_to_long_proof_recovers_the_full_source(self):
    q1 = FakeMessage(2, "catgpt hi")
    a1 = FakeMessage(BOT_ID, "Mrow!", parent=q1)
    q2 = FakeMessage(2, "how do I solve quadratics?", parent=a1)
    text = "Use this:\n$$x = a$$\nor\n$$x = b$$\n" + "Repeat this step for each case. " * 65 + "Done."
    self.assertGreater(len(text), 2000)
    await llm_reply.send_reply(q2, text)
    answer, = q2.sent
    self.assertEqual(len(answer.attachments[0].description), 1024)

    chain = await llm_reply.collect_reply_chain(answer, BOT_ID, resolve, max_turns=3)
    history = await llm_reply.chain_to_history(chain, BOT_ID, describe)
    self.assertEqual(history, [
      {"role": "assistant", "content": "Mrow!"},
      {"role": "user", "content": "Tom: how do I solve quadratics?"},
      {"role": "assistant", "content": text},
    ])

  async def test_turn_limit_counts_answers_not_messages(self):
    q = FakeMessage(2, "question")
    parts = [FakeMessage(BOT_ID, f"part {i}") for i in range(4)]
    parent = q
    for p in parts:
      p.parent = parent
      parent = p
    chain = await llm_reply.collect_reply_chain(parts[-1], BOT_ID, resolve, max_turns=2)
    self.assertEqual(chain, [q] + parts)
    self.assertEqual(await llm_reply.chain_to_history(chain, BOT_ID, describe), [
      {"role": "user", "content": "Tom: question"},
      {"role": "assistant", "content": "part 0\npart 1\npart 2\npart 3"},
    ])
    chain = await llm_reply.collect_reply_chain(parts[-1], BOT_ID, resolve, max_turns=1)
    self.assertEqual(chain, parts)


if __name__ == "__main__":
  unittest.main()
