from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['catgpt_db']

# Collections
acronym_collection = db['acronyms']
gamble_collection = db['gamble']
balance_collection = db['balances']
racers_collection = db['racers']
race_history_collection = db['race_history']
banned_phrase_collection = db['banned_phrases']
init_notification_collection = db['InitNotifications']
contributor_collection = db['contributors']


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
    banned_phrase_collection.create_index([('guild_id', 1), ('phrase', 1)], unique=True)
    init_notification_collection.create_index([('guild_id', 1), ('channel_id', 1)], unique=True)
    contributor_collection.create_index([('guild_id', 1), ('user_id', 1)], unique=True)
    # Ensure money is sourced from balances only and keep gamble schema consistent.
    gamble_collection.update_many({}, {'$unset': {'money': ""}})
    gamble_collection.update_many(
      {'guild_ids': {'$exists': False}},
      {'$set': {'guild_ids': []}}
    )
    print("Database initialized successfully")
  except Exception as e:
    print(f"Error initializing database: {e}")


def set_init_notification(guild_id, guild_name, channel_id, channel_name, enabled):
  """Upsert whether a channel wants a ping when CatGPT comes online."""
  init_notification_collection.update_one(
    {'guild_id': str(guild_id), 'channel_id': str(channel_id)},
    {'$set': {
      'guild_id': str(guild_id),
      'guild_name': guild_name,
      'channel_id': str(channel_id),
      'channel_name': channel_name,
      'enabled': bool(enabled),
    }},
    upsert=True,
  )


def get_init_notification(guild_id, channel_id):
  """Fetch the stored notification preference for a guild's channel, if any."""
  return init_notification_collection.find_one({'guild_id': str(guild_id), 'channel_id': str(channel_id)})


def get_enabled_init_notifications():
  """List all channels that want a ping when CatGPT comes online."""
  return list(init_notification_collection.find({'enabled': True}))


def upsert_contributor(guild_id, user_id, display_name):
  """Cache a user's display name per guild so the dict UI never has to call the Discord API."""
  if not display_name:
    return
  contributor_collection.update_one(
    {'guild_id': str(guild_id), 'user_id': str(user_id)},
    {'$set': {'guild_id': str(guild_id), 'user_id': str(user_id), 'display_name': display_name}},
    upsert=True,
  )


def get_contributor_names(guild_id):
  """Return a {user_id: display_name} map of cached contributors for this guild."""
  docs = contributor_collection.find({'guild_id': str(guild_id)}, {'_id': 0, 'user_id': 1, 'display_name': 1})
  return {doc['user_id']: doc['display_name'] for doc in docs}


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


def get_true_leaderboard(guild_id, limit=10):
  gid = str(guild_id)
  try:
    normalized_limit = max(1, int(limit))
  except (TypeError, ValueError):
    normalized_limit = 10

  docs = list(gamble_collection.find(
    {'guild_ids': gid},
    {'_id': 0, 'user_id': 1, 'name': 1, 'true_money': 1, 'true_winrate_wins': 1, 'true_winrate_total': 1}
  ))

  enriched = []
  for doc in docs:
    try:
      true_money = int(doc.get('true_money') or 0)
    except (TypeError, ValueError):
      true_money = 0
    try:
      wins = int(doc.get('true_winrate_wins') or 0)
      total = int(doc.get('true_winrate_total') or 0)
    except (TypeError, ValueError):
      wins, total = 0, 0
    if total == 0:
      continue
    enriched.append({
      'name': str(doc.get('name', 'Unknown')),
      'true_money': true_money,
      'true_winrate_wins': wins,
      'true_winrate_total': total,
    })

  enriched.sort(key=lambda row: row['true_money'], reverse=True)
  return enriched[:normalized_limit]


def close_db():
  """Close MongoDB connection."""
  try:
    client.close()
    print("Database connection closed")
  except Exception as e:
    print(f"Error closing database: {e}")
