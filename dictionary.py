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


def list_all_acronyms(guild_id):
  """Return all (acronym, phrase) pairs stored for this guild, sorted by acronym."""
  guild_id = str(guild_id)
  results = list(acronym_collection.find(
    {'guild_id': guild_id},
    {'_id': 0, 'acronym': 1, 'phrase': 1}
  ))
  results.sort(key=lambda doc: doc.get('acronym', ''))
  return [(doc['acronym'], doc['phrase']) for doc in results]
