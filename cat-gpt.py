
import os
import json
import discord
import random
from openai import OpenAI
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from gamble import send_gamble_panel, load_gamble_database, save_gamble_database

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
catClient = OpenAI(api_key=os.getenv('CATSEEK'))
bot = commands.Bot(command_prefix="", intents = intents)

api_request_counter = 0
global_count = 0


acronym_map = {}

def load_database():
  global acronym_map
  load_gamble_database()
  try:
    if os.path.exists("./databases/acronyms.json"):
      with open("./databases/acronyms.json", "r") as file:
        acronym_map = json.load(file)
  except Exception as e:
    print(f"Error loading database: {e}")

def save_database():
  save_gamble_database()
  try:   
    with open("./databases/acronyms.json", "w") as file:
      json.dump(acronym_map, file)
  except Exception as e:
    print(f"Error saving database: {e}")

async def chat(msg):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    user_message = msg.content
    system_prompt = "Make the response sound like a cat replied and do not exceed 200 words under any circumstance."

    response = catClient.chat.completions.create(
      model="gpt-4o",
      messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
      ]
    )

    assistant_message = response.choices[0].message.content
    await asyncio.sleep(1)

    return assistant_message

  except Exception as e:
    print(f"Error: {e}")
    return "Merrorr: Something went mwrong mmmmmm"

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

Something = "Hi, I am Catgpt, I respond in meows"
meow = ['meow']
Cat_Gif = "https://tenor.com/view/cat-meow-fat-augh-gif-24948731"
Stickman = "https://cdn.discordapp.com/attachments/1044692376746205244/1154472233805299743/59QL.gif"
WithoutMe = ['shower', 'bed','sleep','kms', 'kill myself']
Blouis = "https://media.discordapp.net/attachments/1167731497134985239/1350984991521378455/blouis.png?ex=67da0bd2&is=67d8ba52&hm=137da4b3c04b2aed10ef63a460142ac89999cf6dd84308031a822592eaff4121&=&format=webp&quality=lossless&width=880&height=1174"
Redward = "https://media.discordapp.net/attachments/1167182348664709256/1351370224133472408/IMG_4161.jpg?ex=67da2118&is=67d8cf98&hm=1d3f5982cef9f011aee2f2dcd2d67fc8af18103d5f274414c2acdd108544ee6d&=&format=webp&width=880&height=1172"
alpha = {
    "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0, "g": 0, "h": 0, "i": 0, 
    "j": 0, "k": 0, "l": 0, "m": 0, "n": 0, "o": 0, "p": 0, "q": 0, "r": 0, 
    "s": 0, "t": 0, "u": 0, "v": 0, "w": 0, "x": 0, "y": 0, "z": 0
}
skulls = {"wtf", "?", "wtf?", "weird guy", "💀"}

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

def acronym(phrase):
  acronym = ""
  print(phrase)
  for word in phrase.split():
    if word[0].isalpha():
      acronym += word[0].upper()
  acronym_map[phrase.lower().strip()] = acronym
  return acronym

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
    matched_phrase = next(
      (phrase for phrase in sorted(acronym_map.keys(), key=len, reverse=True) if phrase in content_lower),
      None
    )
    if matched_phrase:
      await msg.reply("The Big " + acronym_map[matched_phrase])

    if msg.content.startswith("acro"):
      await msg.reply(acronym(msg.content[4:].lower().strip()))
    
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
