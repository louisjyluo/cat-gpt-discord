import os
import json
import asyncio
from openai import OpenAI
from dotenv import load_dotenv
from helpUI import REGULAR_COMMANDS, ADMIN_COMMANDS


load_dotenv()

catClient = OpenAI(
  api_key=os.getenv('LITELLM_API_KEY', 'placeholder'),
  base_url=os.getenv('LITELLM_BASE_URL', 'placeholder'),
)
api_request_counter = 0

def _build_command_reference():
  """Pulls from helpUI's command lists so the LLM's knowledge never drifts from the real `help` output."""
  regular = "\n".join(f"- {c}" for c in REGULAR_COMMANDS)
  admin = "\n".join(f"- {c}" for c in ADMIN_COMMANDS)
  return (
    "Commands any user can type (no prefix needed, just send the message as-is):\n"
    f"{regular}\n\n"
    "Commands restricted to the bot owner, Blouis, only:\n"
    f"{admin}"
  )

COMMAND_REFERENCE = _build_command_reference()
CHAT_SYSTEM_PROMPT = (
  "Make the response sound like a cat replied and do not exceed 200 words under any circumstance. "
  "You are CatGPT, a Discord bot. If the user asks what you can do, how a command works, or for help, "
  "answer using the command reference below instead of guessing. Don't dump the whole list unless asked for it; "
  "just mention the relevant command(s). Never tell the user to run `catgpt <message>` or similar to talk to you — "
  "they're already talking to you right now, so that advice is pointless.\n\n"
  f"{COMMAND_REFERENCE}\n\n"
  "TOOL-CALLABLE commands (you can run these for the user when they clearly ask):\n"
  "- `acro <phrase>` (create_acronym)\n"
  "- `gamble` (open_gamble_panel)\n"
  "- `race` (open_race_panel)\n"
  "- `help` (show_help)\n"
  "- `bank [username]` (show_balance)\n"
  "- `catsum <number>` (summarize_recent_messages)\n"
  "- `dict .` (show_acronym_dictionary)\n"
  "- `blame <ACRO>` (show_blame)\n"
  "- `charades 1`, only when asked for your favourite acro (favourite_acronym)\n"
  "- web search (web_search), when the user asks about current events, recent info, or facts you are unsure of\n\n"
  "NOT tool-callable (the user must run these themselves): lex, unacro, claim, unclaim, charades (any general use), "
  "ban_list, i_hate_fun, i_love_fun, roll, racer/racers, race history, say hi, cat, blouis, redward, "
  "and all owner-only commands (acro *, unacroall, ban, unban, stim, notif, skribbl). "
  "Only call a tool when the user's message is clearly asking for one of the tool-callable commands. "
  "If the user clearly asks you to do one of the NOT tool-callable commands, "
  "call report_unsupported_command with that command's trigger text instead of guessing or chatting normally. "
  "If the user asks what you can do or which commands you can run for them, answer from the two lists above. "
  "Otherwise, just reply normally in character."
)

CHAT_TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "create_acronym",
      "description": "Create/store an acronym for a word or phrase the user explicitly asks to acro.",
      "parameters": {
        "type": "object",
        "properties": {
          "phrase": {
            "type": "string",
            "description": "The exact word or phrase to turn into an acronym, with no extra commentary.",
          }
        },
        "required": ["phrase"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "open_gamble_panel",
      "description": "Open the gambling panel UI. Call when the user asks to gamble, bet, or open the gamble panel.",
      "parameters": {"type": "object", "properties": {}},
    },
  },
  {
    "type": "function",
    "function": {
      "name": "open_race_panel",
      "description": "Open the race panel UI. Call when the user asks to race, start a race, or open the race panel.",
      "parameters": {"type": "object", "properties": {}},
    },
  },
  {
    "type": "function",
    "function": {
      "name": "show_help",
      "description": "Show the bot's help menu. Call when the user asks for help or what commands exist.",
      "parameters": {"type": "object", "properties": {}},
    },
  },
  {
    "type": "function",
    "function": {
      "name": "show_balance",
      "description": "Show a user's money balance. Call when the user asks for their balance or someone else's, e.g. 'whats my balance', 'balance', 'how much money do I have'.",
      "parameters": {
        "type": "object",
        "properties": {
          "username": {
            "type": "string",
            "description": "Mention, user ID, username, or display name whose balance to check. Omit entirely to check the requester's own balance.",
          }
        },
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "summarize_recent_messages",
      "description": "Summarize the most recent messages in the channel. Call when the user asks to summarize recent chat/conversation/sentences without replying to a specific message, e.g. 'summarize this', 'summarize the last couple sentences'.",
      "parameters": {
        "type": "object",
        "properties": {
          "count": {
            "type": "integer",
            "description": "How many recent messages to summarize, between 10 and 50. Default to 10 if the user doesn't specify a number.",
          }
        },
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "show_acronym_dictionary",
      "description": "Show the full list of stored acronyms for this server. Call when the user asks where/how to find all acros or if there's a list of acros.",
      "parameters": {"type": "object", "properties": {}},
    },
  },
  {
    "type": "function",
    "function": {
      "name": "show_blame",
      "description": "Look up who created/owns an acronym. Call when the user asks who made/added/owns an acro, e.g. 'who made this acro? {phrase}', 'who added this? {phrase}'.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "The acronym code (e.g. WTF) or the original phrase the user is asking about.",
          }
        },
        "required": ["query"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "favourite_acronym",
      "description": "Pick a random acro phrase as the bot's favourite. Call when the user asks what your favourite acro/acronym is, e.g. 'what's your favourite acro?'.",
      "parameters": {"type": "object", "properties": {}},
    },
  },
  {
    "type": "function",
    "function": {
      "name": "web_search",
      "description": "Search the web. Call when the user asks to search/google/look something up, or asks about current events, news, or recent facts you can't answer reliably from memory.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "The search query.",
          }
        },
        "required": ["query"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "report_unsupported_command",
      "description": "Call when the user clearly wants to use a bot command that has no tool support (anything not covered by the other tools).",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {
            "type": "string",
            "description": "The exact command trigger text the user should run themselves, e.g. 'claim <ACRO>' or 'charades'.",
          }
        },
        "required": ["command"],
      },
    },
  },
]

async def chat(msg, replied_to=None, image_urls=None, pdfs=None):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    user_message = msg.content
    if replied_to:
      user_message = f"The user is replying to this message:\n\"\"\"\n{replied_to}\n\"\"\"\n\nTheir message: {msg.content}"

    user_content = user_message
    if image_urls or pdfs:
      user_content = [{"type": "text", "text": user_message}] + [
        {"type": "image_url", "image_url": {"url": url}} for url in image_urls or []
      ] + [
        {"type": "file", "file": {"filename": name, "file_data": data_url}} for name, data_url in pdfs or []
      ]

    response = catClient.chat.completions.create(
      model="openai/gpt-luna-latest",
      messages=[
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
      ],
      tools=CHAT_TOOLS,
      tool_choice="auto",
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls or []
    await asyncio.sleep(1)

    if tool_calls:
      call = tool_calls[0]
      try:
        args = json.loads(call.function.arguments or "{}")
      except ValueError:
        args = {}

      if call.function.name == "create_acronym":
        phrase = str(args.get("phrase", "")).strip()
        if phrase:
          return {"action": "acro", "phrase": phrase}
      elif call.function.name == "open_gamble_panel":
        return {"action": "gamble"}
      elif call.function.name == "open_race_panel":
        return {"action": "race"}
      elif call.function.name == "show_help":
        return {"action": "help"}
      elif call.function.name == "show_balance":
        username = str(args.get("username") or "").strip() or None
        return {"action": "balance", "username": username}
      elif call.function.name == "summarize_recent_messages":
        try:
          count = int(args.get("count") or 10)
        except (TypeError, ValueError):
          count = 10
        return {"action": "summarize", "count": count}
      elif call.function.name == "show_acronym_dictionary":
        return {"action": "dict"}
      elif call.function.name == "show_blame":
        query = str(args.get("query", "")).strip()
        if query:
          return {"action": "blame", "query": query}
      elif call.function.name == "favourite_acronym":
        return {"action": "favourite_acro"}
      elif call.function.name == "web_search":
        query = str(args.get("query", "")).strip()
        if query:
          return {"action": "reply", "text": await web_search_reply(user_message, query, image_urls, pdfs)}
      elif call.function.name == "report_unsupported_command":
        command = str(args.get("command", "")).strip()
        if command:
          return {"action": "unsupported", "command": command}

    return {"action": "reply", "text": response_message.content}

  except Exception as e:
    print(f"Error: {e}")
    return {"action": "reply", "text": "Merrorr: Something went mwrong mmmmmm"}


async def web_search_reply(user_message, query, image_urls=None, pdfs=None):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    text = f"{user_message}\n\n(Suggested search: {query})"
    search_input = text
    if image_urls or pdfs:
      search_input = [{"role": "user", "content": [{"type": "input_text", "text": text}] + [
        {"type": "input_image", "image_url": url} for url in image_urls or []
      ] + [
        {"type": "input_file", "filename": name, "file_data": data_url} for name, data_url in pdfs or []
      ]}]

    response = catClient.responses.create(
      model="openai/gpt-luna-latest",
      tools=[{"type": "web_search"}],
      instructions=(
        "You are CatGPT, a Discord bot. Use web search to answer the user's question. "
        "Make the response sound like a cat replied and do not exceed 150 words under any circumstance."
      ),
      input=search_input,
    )
    await asyncio.sleep(1)
    return response.output_text

  except Exception as e:
    print(f"Error: {e}")
    return "Merrorr: I couldn't search the web right meow."


async def favourite_acro_reply(phrase):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    response = catClient.chat.completions.create(
      model="openai/gpt-luna-latest",
      messages=[
        {"role": "system", "content": (
          "You are CatGPT, a Discord bot with a cat personality. Someone asked what your favourite acro is. "
          "Your favourite is the phrase provided by the user. State it exactly as given, then add a short, "
          "playful in-character reason why you love it. Do not exceed 60 words."
        )},
        {"role": "user", "content": phrase}
      ]
    )
    await asyncio.sleep(1)
    return response.choices[0].message.content

  except Exception as e:
    print(f"Error: {e}")
    return f"My favourite acro is **{phrase}**, mrow!"


async def summarize_text(text):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    system_prompt = (
      "You are CatGPT. Summarize the user's provided Discord message(s) in a clear, concise way. "
      "If multiple messages are provided, they are formatted as 'Author: message' and you should summarize the overall conversation. "
      "Keep it under 150 words. Preserve key facts, names, and numbers. "
      "Make sure the summary is shorter than the original content. "
      "Use 1-5 bullet points if necessary. Do not add any information that is not explicitly stated in the original message(s). "
      "Prioritize sounding like a cat."
    )

    response = catClient.chat.completions.create(
      model="openai/gpt-luna-latest",
      messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
      ]
    )

    assistant_message = response.choices[0].message.content
    await asyncio.sleep(1)

    return assistant_message

  except Exception as e:
    print(f"Error: {e}")
    return "Merrorr: I couldn't summarize that right meow."