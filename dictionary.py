import re
from db import acronym_collection


def find_acronyms_in_message(guild_id, message_content):
  """Scan message_content for any known acronyms stored for this guild.
  Returns a dict of {acronym: [phrase, ...]} for each match found."""
  guild_id = str(guild_id)
  results = list(acronym_collection.find(
    {'guild_id': guild_id},
    {'_id': 0, 'acronym': 1, 'phrase': 1}
  ))

  acronym_map = {}
  for doc in results:
    acro = doc['acronym']
    phrase = doc['phrase']
    if acro not in acronym_map:
      acronym_map[acro] = []
    acronym_map[acro].append(phrase)

  found = {}
  upper_content = message_content.upper()
  for acro, phrases in acronym_map.items():
    if not acro:
      continue
    pattern = r'\b' + re.escape(acro) + r'\b'
    if re.search(pattern, upper_content):
      found[acro] = phrases

  return found


def lookup_acronym(guild_id, acronym_str):
  """Find all phrases stored under the given acronym for this guild."""
  guild_id = str(guild_id)
  normalized = acronym_str.strip().upper()
  if not normalized:
    raise ValueError("Acronym cannot be empty.")

  results = list(acronym_collection.find(
    {'guild_id': guild_id, 'acronym': normalized},
    {'_id': 0, 'phrase': 1}
  ))

  return [doc['phrase'] for doc in results]


def claim_acronym(guild_id, acronym_str, user_id, phrase=None):
  """Claim authorship of an acronym if it is currently unclaimed."""
  guild_id = str(guild_id)
  normalized = acronym_str.strip().upper()
  if not normalized:
    raise ValueError("Acronym cannot be empty.")

  query = {'guild_id': guild_id, 'acronym': normalized}
  if phrase is not None:
    query['phrase'] = phrase.lower().strip()

  doc = acronym_collection.find_one(query)
  if doc is None:
    raise ValueError(f"No acronym **{normalized}** found for this server.")

  existing_author = doc.get('author_id')
  if existing_author is not None:
    if existing_author == user_id:
      raise ValueError(f"You already own **{normalized}**.")
    raise ValueError(f"**{normalized}** is already claimed by <@{existing_author}>.")

  acronym_collection.update_one(
    {'_id': doc['_id']},
    {'$set': {'author_id': user_id}}
  )


def unclaim_acronym(guild_id, acronym_str, user_id, phrase=None):
  """Remove authorship from an acronym if the requester is the current owner."""
  guild_id = str(guild_id)
  normalized = acronym_str.strip().upper()
  if not normalized:
    raise ValueError("Acronym cannot be empty.")

  query = {'guild_id': guild_id, 'acronym': normalized}
  if phrase is not None:
    query['phrase'] = phrase.lower().strip()

  doc = acronym_collection.find_one(query)
  if doc is None:
    raise ValueError(f"No acronym **{normalized}** found for this server.")

  existing_author = doc.get('author_id')
  if existing_author is None:
    raise ValueError(f"**{normalized}** is not claimed by anyone.")
  if existing_author != user_id:
    raise ValueError(f"You don't own **{normalized}**. Only <@{existing_author}> can unclaim it.")

  acronym_collection.update_one(
    {'_id': doc['_id']},
    {'$unset': {'author_id': ''}}
  )


def list_all_acronyms(guild_id):
  """Return all (acronym, phrase, author_id) tuples stored for this guild, sorted by acronym."""
  guild_id = str(guild_id)
  results = list(acronym_collection.find(
    {'guild_id': guild_id},
    {'_id': 0, 'acronym': 1, 'phrase': 1, 'author_id': 1}
  ))
  results.sort(key=lambda doc: doc.get('acronym', ''))
  return [(doc['acronym'], doc['phrase'], doc.get('author_id')) for doc in results]
