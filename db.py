from pymongo import MongoClient
import os
import json
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')
BULK_PASSWORD = os.getenv('BULK_PASSWORD') or ""
client = MongoClient(MONGO_URI)
db = client['catgpt_db']

# Collections
acronym_collection = db['acronyms']
gamble_collection = db['gamble']


def init_db():
  """Initialize database indexes for better query performance."""
  try:
    # Create unique index on phrase for acronyms
    acronym_collection.create_index('phrase', unique=True)
    # Create index on user_id for gamble data
    gamble_collection.create_index('user_id', unique=True)
    print("Database initialized successfully")
  except Exception as e:
    print(f"Error initializing database: {e}")


def close_db():
  """Close MongoDB connection."""
  try:
    client.close()
    print("Database connection closed")
  except Exception as e:
    print(f"Error closing database: {e}")


def validate_bulk_password(provided_password):
  """Validate the bulk operation password. Raises ValueError if incorrect."""
  if provided_password != BULK_PASSWORD:
    raise ValueError("Incorrect password.")
  return True


def validate_bulk_target(target):
  """Validate bulk operation target (acro or gamble). Raises ValueError if invalid."""
  if target not in ("acro", "gamble"):
    raise ValueError("Invalid target. Use 'acro' or 'gamble'.")
  return True


def extract_collection_json(target):
  """Export the requested collection as formatted JSON and return content with filename."""
  if target == "acro":
    docs = list(acronym_collection.find({}, {"_id": 0, "phrase": 1, "acronym": 1}))
    formatted = {}
    for doc in docs:
      phrase = doc.get("phrase")
      value = doc.get("acronym")
      if phrase is not None and value is not None:
        formatted[str(phrase)] = value
    return json.dumps(formatted, indent=2, ensure_ascii=False), "acronyms_export.json"
  if target == "gamble":
    docs = list(gamble_collection.find({}, {"_id": 0}))
    formatted = {}
    for doc in docs:
      user_id = doc.get("user_id")
      if user_id is None:
        continue
      player_data = {k: v for k, v in doc.items() if k != "user_id"}
      formatted[str(user_id)] = player_data
    return json.dumps(formatted, indent=2, ensure_ascii=False), "gamble_export.json"

  raise ValueError("Unsupported target. Use 'acro' or 'gamble'.")


def validate_acronym_data(data):
  """Validate acronym JSON structure. Expected: {phrase: acronym_string}"""
  if not isinstance(data, dict):
    raise ValueError("Acronym data must be a JSON object/dictionary")
  
  for phrase, acronym in data.items():
    if not isinstance(phrase, str) or not phrase.strip():
      raise ValueError(f"Acronym phrase must be a non-empty string, got: {phrase}")
    if not isinstance(acronym, str) or not acronym.strip():
      raise ValueError(f"Acronym value must be a non-empty string, got: {acronym}")
  
  return True


def validate_gamble_data(data):
  """Validate gamble JSON structure. Expected: {user_id: {player_data}}"""
  if not isinstance(data, dict):
    raise ValueError("Gamble data must be a JSON object/dictionary")
  
  for user_id, player_data in data.items():
    # Validate user_id is a string of digits
    if not isinstance(user_id, str) or not user_id.isdigit():
      raise ValueError(f"User ID must be a string of digits, got: {user_id}")
    
    if not isinstance(player_data, dict):
      raise ValueError(f"Player data for user {user_id} must be an object, got: {type(player_data)}")
    
    # Validate required fields
    if "money" not in player_data:
      raise ValueError(f"Player data for user {user_id} missing required field: money")
    
    if not isinstance(player_data["money"], (int, float)) or player_data["money"] < 1:
      raise ValueError(f"Player money for user {user_id} must be a number >= 1, got: {player_data['money']}")
    
    # Validate optional fields if present
    if "name" in player_data and not isinstance(player_data["name"], str):
      raise ValueError(f"Player name for user {user_id} must be a string, got: {type(player_data['name'])}")
    
    if "win_streak" in player_data and not isinstance(player_data["win_streak"], int):
      raise ValueError(f"Win streak for user {user_id} must be an integer, got: {type(player_data['win_streak'])}")
    
    if "last_amount_change" in player_data and not isinstance(player_data["last_amount_change"], (int, float)):
      raise ValueError(f"Last amount change for user {user_id} must be a number, got: {type(player_data['last_amount_change'])}")
  
  return True


def bulk_upload_acronyms(data):
  """Bulk upload acronym data to database. Data format: {phrase: acronym}"""
  validate_acronym_data(data)
  
  inserted = 0
  updated = 0
  try:
    for phrase, acronym in data.items():
      result = acronym_collection.update_one(
        {'phrase': phrase.lower().strip()},
        {'$set': {'phrase': phrase.lower().strip(), 'acronym': acronym}},
        upsert=True
      )
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1
    
    return f"Successfully uploaded {len(data)} acronyms (Inserted: {inserted}, Updated: {updated})"
  except Exception as e:
    raise Exception(f"Error uploading acronyms: {e}")


def bulk_upload_gamble(data):
  """Bulk upload gamble data to database. Data format: {user_id: {player_data}}"""
  validate_gamble_data(data)
  
  inserted = 0
  updated = 0
  try:
    for user_id, player_data in data.items():
      # Add user_id to the document
      doc = {'user_id': user_id, **player_data}
      result = gamble_collection.update_one(
        {'user_id': user_id},
        {'$set': doc},
        upsert=True
      )
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1
    
    return f"Successfully uploaded {len(data)} players (Inserted: {inserted}, Updated: {updated})"
  except Exception as e:
    raise Exception(f"Error uploading gamble data: {e}")
