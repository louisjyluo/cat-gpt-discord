import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import llm


class FakeClient:
  def __init__(self):
    self.started = asyncio.Event()
    self.release = asyncio.Event()
    self.active_requests = 0
    self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create_chat))
    self.responses = SimpleNamespace(create=self.create_response)

  async def wait_for_release(self):
    self.active_requests += 1
    if self.active_requests == 4:
      self.started.set()
    await self.release.wait()

  async def create_chat(self, **kwargs):
    await self.wait_for_release()
    message = SimpleNamespace(content="Meow", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])

  async def create_response(self, **kwargs):
    await self.wait_for_release()
    return SimpleNamespace(output_text="Search result")


class LlmConcurrencyTests(unittest.IsolatedAsyncioTestCase):
  async def test_llm_calls_overlap_and_leave_event_loop_available(self):
    fake_client = FakeClient()
    message = SimpleNamespace(content="catgpt hello")

    with patch.object(llm, "catClient", fake_client):
      tasks = [
        asyncio.create_task(llm.chat(message)),
        asyncio.create_task(llm.web_search_reply("What happened?", "news")),
        asyncio.create_task(llm.favourite_acro_reply("CAT")),
        asyncio.create_task(llm.summarize_text("A long conversation")),
      ]
      try:
        await asyncio.wait_for(fake_client.started.wait(), timeout=2)
        self.assertEqual(fake_client.active_requests, 4)
        other_command = await asyncio.wait_for(asyncio.sleep(0, result="other command"), timeout=1)
        self.assertEqual(other_command, "other command")
      finally:
        fake_client.release.set()
        results = await asyncio.gather(*tasks)

    self.assertEqual(results, [
      {"action": "reply", "text": "Meow"},
      "Search result",
      "Meow",
      "Meow",
    ])


if __name__ == "__main__":
  unittest.main()
