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
balance_collection = db['balances']
racers_collection = db['racers']
race_history_collection = db['race_history']


BULK_TARGET_ALIASES = {
  'acro': 'acro',
  'acronym': 'acro',
  'acronyms': 'acro',
  'gamble': 'gamble',
  'balances': 'balances',
  'balance': 'balances',
  'racers': 'racers',
  'race_history': 'race_history',
  'racehistory': 'race_history',
}


def init_db():
  """Initialize database indexes for better query performance."""
  try:
    # Create unique index on phrase for acronyms
    acronym_collection.create_index('phrase', unique=True)
    # Create index on user_id for gamble data
    gamble_collection.create_index('user_id', unique=True)
    # Create index on user_id for shared balances
    balance_collection.create_index('user_id', unique=True)
    # Create indexes for persisted racers
    racers_collection.create_index([('guild_id', 1), ('racer_id', 1)], unique=True)
    racers_collection.create_index([('guild_id', 1), ('owner_id', 1)])
    # Create index for race history dedupe
    race_history_collection.create_index([('guild_id', 1), ('race_signature', 1)], unique=True)
    print("Database initialized successfully")
  except Exception as e:
    print(f"Error initializing database: {e}")


def log_race_result(guild_id, race_signature, turns, results):
  """Persist final race standings. Returns True when inserted, False if duplicate signature."""
  payload = {
    'guild_id': str(guild_id),
    'race_signature': str(race_signature),
    'turns': int(turns),
    'results': results,
  }
  result = race_history_collection.update_one(
    {'guild_id': str(guild_id), 'race_signature': str(race_signature)},
    {'$setOnInsert': payload},
    upsert=True,
  )
  return bool(result.upserted_id)


def get_recent_race_history(guild_id, limit=10):
  """Load recent race history records for a guild (most recent first)."""
  try:
    normalized_limit = max(1, int(limit))
  except (TypeError, ValueError):
    normalized_limit = 10

  cursor = race_history_collection.find(
    {'guild_id': str(guild_id)},
    {'_id': 0, 'guild_id': 0}
  ).sort('_id', -1).limit(normalized_limit)
  return list(cursor)


def load_racer_records(guild_id):
  """Load all persisted racer records for a guild."""
  return list(racers_collection.find({'guild_id': str(guild_id)}, {'_id': 0}))


def upsert_racer_record(guild_id, racer_record):
  """Upsert one persisted racer record for a guild."""
  record = {**racer_record, 'guild_id': str(guild_id)}
  racers_collection.update_one(
    {'guild_id': str(guild_id), 'racer_id': record['racer_id']},
    {'$set': record},
    upsert=True,
  )


def delete_racer_record(guild_id, racer_id):
  """Delete one persisted racer record for a guild."""
  racers_collection.delete_one({'guild_id': str(guild_id), 'racer_id': str(racer_id)})


def delete_guild_racer_records(guild_id):
  """Delete all persisted racer records for a guild."""
  racers_collection.delete_many({'guild_id': str(guild_id)})


def get_user_balance(user_id, default_balance=1):
  """Get shared user balance used by both gamble and race systems."""
  uid = str(user_id)
  doc = balance_collection.find_one({'user_id': uid})
  if not doc:
    return int(default_balance)

  amount = doc.get('money', default_balance)
  try:
    amount = int(amount)
  except (TypeError, ValueError):
    amount = int(default_balance)
  return max(1, amount)


def set_user_balance(user_id, amount):
  """Set shared user balance and return normalized stored value."""
  uid = str(user_id)
  try:
    normalized = int(amount)
  except (TypeError, ValueError):
    normalized = 1
  normalized = max(1, normalized)

  balance_collection.update_one(
    {'user_id': uid},
    {'$set': {'user_id': uid, 'money': normalized}},
    upsert=True
  )
  return normalized


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
  """Normalize and validate bulk operation target. Raises ValueError if invalid."""
  normalized = str(target).strip().lower()
  canonical = BULK_TARGET_ALIASES.get(normalized)
  if canonical is None:
    allowed = "acro, gamble, balances, racers, race_history"
    raise ValueError(f"Invalid target. Use one of: {allowed}.")
  return canonical


def extract_collection_json(target):
  """Export the requested collection as formatted JSON and return content with filename."""
  target = validate_bulk_target(target)

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
      player_data["money"] = get_user_balance(user_id)
      formatted[str(user_id)] = player_data
    return json.dumps(formatted, indent=2, ensure_ascii=False), "gamble_export.json"

  if target == "balances":
    docs = list(balance_collection.find({}, {"_id": 0}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "balances_export.json"

  if target == "racers":
    docs = list(racers_collection.find({}, {"_id": 0}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "racers_export.json"

  if target == "race_history":
    docs = list(race_history_collection.find({}, {"_id": 0}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "race_history_export.json"

  raise ValueError("Unsupported target.")


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
    
    # Validate optional shared money field if present
    if "money" in player_data:
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


def validate_balance_data(data):
  """Validate balances JSON structure.

  Accepted:
  - [{user_id, money, ...optional fields...}, ...]
  - {user_id: {money: <number>, ...optional fields...}, ...}
  """
  if isinstance(data, list):
    for row in data:
      if not isinstance(row, dict):
        raise ValueError("Each balances row must be an object.")
      user_id = row.get("user_id")
      if user_id is None or not str(user_id).strip().isdigit():
        raise ValueError(f"Balances row missing valid user_id: {row}")
      if "money" in row and (not isinstance(row["money"], (int, float)) or row["money"] < 1):
        raise ValueError(f"Balances row has invalid money value: {row}")
    return True

  if isinstance(data, dict):
    for user_id, row in data.items():
      if not str(user_id).isdigit():
        raise ValueError(f"Balances key user_id must be digits, got: {user_id}")
      if not isinstance(row, dict):
        raise ValueError(f"Balances data for user {user_id} must be an object.")
      money = row.get("money")
      if money is None:
        raise ValueError(f"Balances data for user {user_id} must include money.")
      if not isinstance(money, (int, float)) or money < 1:
        raise ValueError(f"Balances money for user {user_id} must be >= 1.")
    return True

  raise ValueError("Balances data must be either a JSON array or object.")


def validate_racers_data(data):
  """Validate racers JSON structure. Expected: [{guild_id, racer_id, ...}, ...]"""
  if not isinstance(data, list):
    raise ValueError("Racers data must be a JSON array of racer records.")

  for row in data:
    if not isinstance(row, dict):
      raise ValueError("Each racers row must be an object.")
    if not str(row.get("guild_id", "")).strip():
      raise ValueError(f"Racers row missing guild_id: {row}")
    if not str(row.get("racer_id", "")).strip():
      raise ValueError(f"Racers row missing racer_id: {row}")

  return True


def validate_race_history_data(data):
  """Validate race history JSON structure. Expected: [{guild_id, race_signature, ...}, ...]"""
  if not isinstance(data, list):
    raise ValueError("Race history data must be a JSON array of race records.")

  for row in data:
    if not isinstance(row, dict):
      raise ValueError("Each race history row must be an object.")
    if not str(row.get("guild_id", "")).strip():
      raise ValueError(f"Race history row missing guild_id: {row}")
    if not str(row.get("race_signature", "")).strip():
      raise ValueError(f"Race history row missing race_signature: {row}")

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
      shared_money = player_data.get("money")
      if shared_money is not None:
        set_user_balance(user_id, shared_money)

      # Add user_id to the document
      doc_payload = {k: v for k, v in player_data.items() if k != "money"}
      doc = {'user_id': user_id, **doc_payload}
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


def bulk_upload_balances(data):
  """Bulk upload balances data."""
  validate_balance_data(data)

  inserted = 0
  updated = 0
  try:
    if isinstance(data, dict):
      items = []
      for user_id, row in data.items():
        items.append({'user_id': str(user_id), **row})
    else:
      items = data

    for row in items:
      user_id = str(row.get('user_id')).strip()
      doc = {k: v for k, v in row.items() if k != '_id'}
      doc['user_id'] = user_id

      if 'guild_id' in doc and str(doc.get('guild_id')).strip():
        doc['guild_id'] = str(doc['guild_id'])
        query = {'guild_id': doc['guild_id'], 'user_id': user_id}
      else:
        query = {'user_id': user_id}

      result = balance_collection.update_one(query, {'$set': doc}, upsert=True)
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1

    return f"Successfully uploaded {len(items)} balances (Inserted: {inserted}, Updated: {updated})"
  except Exception as e:
    raise Exception(f"Error uploading balances data: {e}")


def bulk_upload_racers(data):
  """Bulk upload racers data. Data format: [{guild_id, racer_id, ...}, ...]"""
  validate_racers_data(data)

  inserted = 0
  updated = 0
  try:
    for row in data:
      guild_id = str(row.get('guild_id')).strip()
      racer_id = str(row.get('racer_id')).strip()
      doc = {k: v for k, v in row.items() if k != '_id'}
      doc['guild_id'] = guild_id
      doc['racer_id'] = racer_id

      result = racers_collection.update_one(
        {'guild_id': guild_id, 'racer_id': racer_id},
        {'$set': doc},
        upsert=True
      )
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1

    return f"Successfully uploaded {len(data)} racers (Inserted: {inserted}, Updated: {updated})"
  except Exception as e:
    raise Exception(f"Error uploading racers data: {e}")


def bulk_upload_race_history(data):
  """Bulk upload race history data. Data format: [{guild_id, race_signature, ...}, ...]"""
  validate_race_history_data(data)

  inserted = 0
  updated = 0
  try:
    for row in data:
      guild_id = str(row.get('guild_id')).strip()
      race_signature = str(row.get('race_signature')).strip()
      doc = {k: v for k, v in row.items() if k != '_id'}
      doc['guild_id'] = guild_id
      doc['race_signature'] = race_signature

      result = race_history_collection.update_one(
        {'guild_id': guild_id, 'race_signature': race_signature},
        {'$set': doc},
        upsert=True
      )
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1

    return f"Successfully uploaded {len(data)} race history records (Inserted: {inserted}, Updated: {updated})"
  except Exception as e:
    raise Exception(f"Error uploading race history data: {e}")


def bulk_upload_collection(target, data):
  """Dispatch bulk upload by target key."""
  canonical = validate_bulk_target(target)
  if canonical == 'acro':
    return bulk_upload_acronyms(data)
  if canonical == 'gamble':
    return bulk_upload_gamble(data)
  if canonical == 'balances':
    return bulk_upload_balances(data)
  if canonical == 'racers':
    return bulk_upload_racers(data)
  if canonical == 'race_history':
    return bulk_upload_race_history(data)
  raise ValueError(f"Unsupported upload target: {canonical}")
