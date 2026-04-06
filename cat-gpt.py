
import os
import discord
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from discord.ext import commands
from dotenv import load_dotenv
from gamble import send_gamble_panel, load_gamble_database, save_gamble_database
from acronym import acronym, load_acronym_database, save_acronym_database, get_matching_acronym
from llm import chat

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="", intents = intents)

global_count = 0

def load_database():
  load_gamble_database()
  load_acronym_database()

def save_database():
  save_gamble_database()
  save_acronym_database()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

Something = "Hi, I am Catgpt, I respond in meows"
meow = ['meow']
Cat_Gif = "https://tenor.com/view/cat-meow-fat-augh-gif-24948731"
WithoutMe = ['shower', 'bed','sleep','kms', 'kill myself']
Blouis = "https://media.discordapp.net/attachments/1167731497134985239/1350984991521378455/blouis.png?ex=67da0bd2&is=67d8ba52&hm=137da4b3c04b2aed10ef63a460142ac89999cf6dd84308031a822592eaff4121&=&format=webp&quality=lossless&width=880&height=1174"
Redward = "https://media.discordapp.net/attachments/1167182348664709256/1351370224133472408/IMG_4161.jpg?ex=67da2118&is=67d8cf98&hm=1d3f5982cef9f011aee2f2dcd2d67fc8af18103d5f274414c2acdd108544ee6d&=&format=webp&width=880&height=1172"
alpha = {
    "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0, "g": 0, "h": 0, "i": 0, 
    "j": 0, "k": 0, "l": 0, "m": 0, "n": 0, "o": 0, "p": 0, "q": 0, "r": 0, 
    "s": 0, "t": 0, "u": 0, "v": 0, "w": 0, "x": 0, "y": 0, "z": 0
}
skulls = {"wtf", "?", "wtf?", "weird guy", "💀"}
protected_acro_phrases = {
    "catgpt",
    "lex",
    "acro",
    "count",
    "roll",
    "gamble",
    "say hi",
    "cat",
    "blouis",
    "redward",
    "help"
}
HELP_MESSAGE = (
  "**CatGPT Commands**\n"
  "- `catgpt <message>`: Ask CatGPT a question.\n"
  "- `lex <word>`: Alphabetically sorts letters in the word.\n"
  "- `acro <phrase>`: Creates/stores an acronym for a word or phrase.\n"
  "- `count`: Increases and shows the current counter.\n"
  "- `roll`: Rolls a random number from 1 to 1000.\n"
  "- `gamble`: Opens the gambling panel.\n"
  "- `say hi`: Bot says hello.\n"
  "- `cat`: Sends the cat gif.\n"
  "- `blouis`: Sends the Blouis image.\n"
  "- `redward`: Sends the Redward image.\n"
  "- `help`: Shows this command list."
)

def alphabetize(word):
    lower_case = word.lower()
    for letter in lower_case:
      if letter in alpha.keys():
        alpha[letter] += 1

    ret = ""
    for letter in alpha:
        ret += letter * alpha[letter]

    for letter in alpha:
        alpha[letter] = 0
  
    return ret
  
def game():
  sum = random.randint(1,1000)
  return sum

def counter():
  try:
    global global_count 
    global_count += 1
    return global_count
  except Exception as e:
    return "bro how did u run into this error :skull:"

def meowSeparate(msg):
  return msg.replace("meow", "**meow**")

@client.event
async def on_message(msg):
  if msg.content.startswith("catgpt"):
      await msg.reply(await chat(msg))
  else: 
    if msg.author == client.user:
      return 
    if msg.content.startswith("lex"):
      await msg.reply(alphabetize(msg.content[3:]))
    
    content_lower = msg.content.lower().strip()
    matched_acronym = get_matching_acronym(content_lower)
    if matched_acronym:
      await msg.reply("The Big " + matched_acronym)

    if msg.content.startswith("acro"):
      acro_input = msg.content[4:].lower().strip()
      if acro_input in protected_acro_phrases:
        await msg.reply("You can't acro bot commands.")
      elif acro_input:
        await msg.reply(acronym(acro_input))
      else:
        await msg.reply("Usage: acro <word or phrase>")

    if msg.content.startswith("help"):
      await msg.reply(HELP_MESSAGE)
    
    if msg.content.startswith("count"):
      await msg.reply(counter())
  
    if msg.content.startswith("roll"):
      await msg.reply(game())

    if msg.content.startswith("gamble"):
      await send_gamble_panel(msg)
      
    if msg.content.startswith("say hi"):
      await msg.reply(Something)
  
    if msg.content.startswith("cat"):
      await msg.reply(Cat_Gif)
     
    if msg.content.startswith("blouis"):
      await msg.reply(Blouis) 
     
    if msg.content.startswith("redward"):  
      await msg.reply(Redward) 

    if any(word in msg.content for word in skulls):
       await msg.add_reaction("💀") 
  
    if any(word in msg.content for word in meow):
      await msg.reply(meowSeparate(msg.content)) 
  
    if any(word in msg.content for word in WithoutMe):
      await msg.reply("without me? :pleading_face:") 

try:
  load_database()
  token = os.getenv("TOKEN") or ""
  if token == "":
    raise Exception("Please add your token to the Secrets pane.")
  client.run(token)
except discord.HTTPException as e:
    if e.status == 429:
        print(
            "The Discord servers denied the connection for making too many requests"
        )
        print(
            "Get help from https://stackoverflow.com/questions/66724687/in-discord-py-how-to-solve-the-error-for-toomanyrequests"
        )
    else:
        raise e
finally:
  save_database()
