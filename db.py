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
    # Scope acronym uniqueness by guild and keep gamble/balance per user.
    acronym_collection.create_index([('guild_id', 1), ('phrase', 1)], unique=True)
    gamble_collection.create_index('user_id', unique=True)
    gamble_collection.create_index([('guild_ids', 1), ('user_id', 1)])
    balance_collection.create_index('user_id', unique=True)
    # Create indexes for persisted racers
    racers_collection.create_index([('guild_id', 1), ('racer_id', 1)], unique=True)
    racers_collection.create_index([('guild_id', 1), ('owner_id', 1)])
    # Create index for race history dedupe
    race_history_collection.create_index([('guild_id', 1), ('race_signature', 1)], unique=True)
    # Ensure money is sourced from balances only and keep gamble schema consistent.
    gamble_collection.update_many({}, {'$unset': {'money': ""}})
    gamble_collection.update_many(
      {'guild_ids': {'$exists': False}},
      {'$set': {'guild_ids': []}}
    )
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


def get_user_balance(guild_id_or_user_id, user_id=None, default_balance=1):
  """Get a shared user balance used by both gamble and race systems."""
  uid = str(guild_id_or_user_id if user_id is None else user_id)
  doc = balance_collection.find_one({'user_id': uid})
  if not doc:
    return int(default_balance)

  amount = doc.get('money', default_balance)
  try:
    amount = int(amount)
  except (TypeError, ValueError):
    amount = int(default_balance)
  return max(1, amount)


def set_user_balance(guild_id_or_user_id, user_id=None, amount=None):
  """Set a shared user balance and return normalized stored value."""
  if amount is None:
    uid = str(guild_id_or_user_id)
    value = user_id
  else:
    uid = str(user_id)
    value = amount
  try:
    normalized = int(value)
  except (TypeError, ValueError):
    normalized = 1
  normalized = max(1, normalized)

  balance_collection.update_one(
    {'user_id': uid},
    {'$set': {'user_id': uid, 'money': normalized}},
    upsert=True
  )
  return normalized


def get_gamble_leaderboard(guild_id, limit=10):
  gid = str(guild_id)
  try:
    normalized_limit = max(1, int(limit))
  except (TypeError, ValueError):
    normalized_limit = 10

  docs = list(gamble_collection.find(
    {'guild_ids': gid},
    {'_id': 0, 'user_id': 1, 'name': 1}
  ))

  enriched = []
  for doc in docs:
    user_id = str(doc.get('user_id', ''))
    if user_id == "":
      continue
    row = {
      'user_id': user_id,
      'name': str(doc.get('name', 'Unknown')),
    }
    row['money'] = get_user_balance(user_id)
    enriched.append(row)

  enriched.sort(key=lambda row: int(row.get('money', 1)), reverse=True)
  return enriched[:normalized_limit]


def close_db():
  """Close MongoDB connection."""
  try:
    client.close()
    print("Database connection closed")
  except Exception as e:
    print(f"Error closing database: {e}")


def validate_bulk_password(provided_user_id):
  """Validate bulk operation access. Raises ValueError unless the caller is Blouis."""
  if str(provided_user_id) != str(os.getenv('BLOUIS_ID') or ""):
    raise ValueError("You are not authorized to use bulk extract/upload.")
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
    docs = list(acronym_collection.find({}, {"_id": 0, "guild_id": 1, "phrase": 1, "acronym": 1}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "acronyms_export.json"
  if target == "gamble":
    docs = list(gamble_collection.find({}, {"_id": 0}))
    formatted = []
    for doc in docs:
      doc.pop("money", None)
      user_id = doc.get("user_id")
      if user_id is None:
        continue
      doc.pop("guild_id", None)
      formatted.append(dict(doc))
    return json.dumps(formatted, indent=2, ensure_ascii=False), "gamble_export.json"

  if target == "balances":
    docs = list(balance_collection.find({}, {"_id": 0}))
    for doc in docs:
      doc.pop("guild_id", None)
    return json.dumps(docs, indent=2, ensure_ascii=False), "balances_export.json"

  if target == "racers":
    docs = list(racers_collection.find({}, {"_id": 0}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "racers_export.json"

  if target == "race_history":
    docs = list(race_history_collection.find({}, {"_id": 0}))
    return json.dumps(docs, indent=2, ensure_ascii=False), "race_history_export.json"

  raise ValueError("Unsupported target.")


def validate_acronym_data(data):
  """Validate acronym JSON structure. Expected: [{guild_id, phrase, acronym}, ...]"""
  if not isinstance(data, list):
    raise ValueError("Acronym data must be a JSON array of objects")

  for row in data:
    if not isinstance(row, dict):
      raise ValueError("Each acronym row must be an object.")
    if not str(row.get("guild_id", "")).strip():
      raise ValueError(f"Acronym row missing guild_id: {row}")
    phrase = row.get("phrase")
    acronym = row.get("acronym")
    if not isinstance(phrase, str) or not phrase.strip():
      raise ValueError(f"Acronym phrase must be a non-empty string, got: {phrase}")
    if not isinstance(acronym, str) or not acronym.strip():
      raise ValueError(f"Acronym value must be a non-empty string, got: {acronym}")
  
  return True


def validate_gamble_data(data):
  """Validate gamble JSON structure. Expected: [{user_id, ...player_data...}, ...]"""
  if not isinstance(data, list):
    raise ValueError("Gamble data must be a JSON array of objects")

  for row in data:
    if not isinstance(row, dict):
      raise ValueError("Each gamble row must be an object.")
    user_id = row.get("user_id")
    if not isinstance(user_id, str) or not user_id.isdigit():
      raise ValueError(f"User ID must be a string of digits, got: {user_id}")

    if "money" in row and (not isinstance(row["money"], (int, float)) or row["money"] < 1):
      raise ValueError(f"Player money for user {user_id} must be a number >= 1, got: {row['money']}")

    if "name" in row and not isinstance(row["name"], str):
      raise ValueError(f"Player name for user {user_id} must be a string, got: {type(row['name'])}")

    if "guild_ids" in row:
      guild_ids = row["guild_ids"]
      if not isinstance(guild_ids, list):
        raise ValueError(f"guild_ids for user {user_id} must be a list of guild IDs.")
      for gid in guild_ids:
        if not str(gid).strip().isdigit():
          raise ValueError(f"Invalid guild_id for user {user_id}: {gid}")

    if "win_streak" in row and not isinstance(row["win_streak"], int):
      raise ValueError(f"Win streak for user {user_id} must be an integer, got: {type(row['win_streak'])}")

    if "last_amount_change" in row and not isinstance(row["last_amount_change"], (int, float)):
      raise ValueError(f"Last amount change for user {user_id} must be a number, got: {type(row['last_amount_change'])}")

    if "gambler_stars" in row:
      stars = row["gambler_stars"]
      if not isinstance(stars, int) or stars < 0:
        raise ValueError(f"gambler_stars for user {user_id} must be an integer >= 0, got: {stars}")

    if "ascension_abilities" in row:
      abilities = row["ascension_abilities"]
      if not isinstance(abilities, dict):
        raise ValueError(f"ascension_abilities for user {user_id} must be an object, got: {type(abilities)}")

      def _bounded_int(key, min_value, max_value):
        if key not in abilities:
          return
        value = abilities[key]
        if not isinstance(value, int) or value < min_value or value > max_value:
          raise ValueError(
            f"ascension_abilities.{key} for user {user_id} must be int {min_value}-{max_value}, got: {value}"
          )

      _bounded_int("foundation", 0, 5)
      _bounded_int("fickle", 0, 2)
      _bounded_int("influence", 0, 3)
      _bounded_int("heavy_die", 0, 3)
      _bounded_int("sage", 0, 3)
      _bounded_int("passion", 0, 3)

      for flag_key in ("unbounded", "blessed", "greed"):
        if flag_key in abilities and not isinstance(abilities[flag_key], bool):
          raise ValueError(
            f"ascension_abilities.{flag_key} for user {user_id} must be boolean, got: {abilities[flag_key]}"
          )
  
  return True


def validate_balance_data(data):
  """Validate balances JSON structure.

  Expected:
  - [{user_id, money, ...optional fields...}, ...]
  """
  if not isinstance(data, list):
    raise ValueError("Balances data must be a JSON array.")

  for row in data:
    if not isinstance(row, dict):
      raise ValueError("Each balances row must be an object.")
    user_id = row.get("user_id")
    if user_id is None or not str(user_id).strip().isdigit():
      raise ValueError(f"Balances row missing valid user_id: {row}")
    if "money" not in row:
      raise ValueError(f"Balances row missing money: {row}")
    if not isinstance(row["money"], (int, float)) or row["money"] < 1:
      raise ValueError(f"Balances row has invalid money value: {row}")

  return True


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
  """Bulk upload acronym data to database. Data format: [{guild_id, phrase, acronym}, ...]"""
  validate_acronym_data(data)
  
  inserted = 0
  updated = 0
  try:
    for row in data:
      guild_id = str(row.get('guild_id')).strip()
      phrase = str(row.get('phrase')).lower().strip()
      acronym = row.get('acronym')
      result = acronym_collection.update_one(
        {'guild_id': guild_id, 'phrase': phrase},
        {'$set': {'guild_id': guild_id, 'phrase': phrase, 'acronym': acronym}},
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
  """Bulk upload gamble data to database. Data format: [{user_id, ...player_data...}, ...]"""
  validate_gamble_data(data)
  
  inserted = 0
  updated = 0
  try:
    for row in data:
      user_id = str(row.get('user_id')).strip()
      shared_money = row.get("money")
      if shared_money is not None:
        set_user_balance(user_id, shared_money)

      doc = {k: v for k, v in row.items() if k not in ("money", "_id", "guild_id")}
      guild_ids = doc.get('guild_ids') or []
      if not isinstance(guild_ids, list):
        guild_ids = [guild_ids]
      doc['guild_ids'] = list(dict.fromkeys([str(gid).strip() for gid in guild_ids if str(gid).strip()]))
      doc['user_id'] = user_id
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
    for row in data:
      user_id = str(row.get('user_id')).strip()
      doc = {k: v for k, v in row.items() if k not in ('_id', 'guild_id')}
      doc['user_id'] = user_id

      result = balance_collection.update_one({'user_id': user_id}, {'$set': doc}, upsert=True)
      if result.upserted_id:
        inserted += 1
      else:
        updated += 1

    return f"Successfully uploaded {len(data)} balances (Inserted: {inserted}, Updated: {updated})"
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
