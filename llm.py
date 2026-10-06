import os
import json
import asyncio
from openai import OpenAI
from dotenv import load_dotenv
from helpUI import REGULAR_COMMANDS, ADMIN_COMMANDS


load_dotenv()

catClient = OpenAI(api_key=os.getenv('CATGPT'))
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
  "You also have tools to directly perform simple actions when the user clearly asks for them: "
  "creating an acronym for a phrase, opening the gamble panel, opening the race panel, showing the help menu, "
  "checking a balance, summarizing recent channel messages, listing all stored acronyms, or looking up who made/owns an acronym. "
  "Only call a tool when the user's message is clearly asking for one of those things. "
  "If the user's message clearly asks for a DIFFERENT command from the reference above (one with no matching tool, e.g. "
  "lex, unacro, claim, unclaim, charades, stim, ban, unban, ban_list, racer/racers, race history, notif, i_hate_fun, i_love_fun), "
  "call report_unsupported_command with that command's trigger text instead of guessing or chatting normally. "
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

async def chat(msg):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    user_message = msg.content

    response = catClient.chat.completions.create(
      model="gpt-5.4-mini",
      messages=[
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
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
      elif call.function.name == "report_unsupported_command":
        command = str(args.get("command", "")).strip()
        if command:
          return {"action": "unsupported", "command": command}

    return {"action": "reply", "text": response_message.content}

  except Exception as e:
    print(f"Error: {e}")
    return {"action": "reply", "text": "Merrorr: Something went mwrong mmmmmm"}


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
      model="gpt-5.4-mini",
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