from db import acronym_collection


def load_acronym_database():
  """Load all acronyms from MongoDB into memory (optional, can query directly)."""
  try:
    acronyms = list(acronym_collection.find({}))
    print(f"Loaded {len(acronyms)} acronyms from database")
  except Exception as e:
    print(f"Error loading acronym database: {e}")


def save_acronym_database():
  """MongoDB automatically persists data, but this is kept for API compatibility."""
  try:
    print("Acronym database is auto-persisted in MongoDB")
  except Exception as e:
    print(f"Error in save_acronym_database: {e}")


def acronym(guild_id, phrase):
  guild_id = str(guild_id)
  normalized = phrase.strip()
  if len(normalized.replace(" ", "")) < 4:
    raise ValueError("Phrase must be at least 4 characters long.")
  if len(phrase.split()) == 1:
    return word_acronym(guild_id, phrase)
  return phrase_acronym(guild_id, phrase)


def word_acronym(guild_id, word):
  normalized = word.strip()
  if len(normalized) < 4:
    raise ValueError("Word must be at least 4 characters long.")

  generated_acronym = word[-(len(word) // 2):].upper()
  # Upsert: update if exists, insert if not
  acronym_collection.update_one(
    {'guild_id': guild_id, 'phrase': word.lower().strip()},
    {'$set': {'guild_id': guild_id, 'phrase': word.lower().strip(), 'acronym': generated_acronym}},
    upsert=True
  )
  return generated_acronym


def phrase_acronym(guild_id, phrase):
  generated_acronym = ""
  for word in phrase.split():
    if word[0].isalpha():
      generated_acronym += word[0].upper()
  
  # Upsert: update if exists, insert if not
  acronym_collection.update_one(
    {'guild_id': guild_id, 'phrase': phrase.lower().strip()},
    {'$set': {'guild_id': guild_id, 'phrase': phrase.lower().strip(), 'acronym': generated_acronym}},
    upsert=True
  )
  return generated_acronym


def get_matching_acronym(guild_id, content_lower):
  """Find the longest matching acronym phrase in content."""
  try:
    all_acronyms = list(acronym_collection.find({'guild_id': str(guild_id)}))
    all_acronyms.sort(key=lambda x: len(x['phrase']), reverse=True)
    
    for entry in all_acronyms:
      if entry['phrase'] in content_lower:
        return entry['acronym']
    
    return None
  except Exception as e:
    print(f"Error getting matching acronym: {e}")
    return None


def unacronym(guild_id, phrase):
  guild_id = str(guild_id)
  normalized = phrase.strip().lower()
  if not normalized:
    raise ValueError("Word or phrase cannot be empty.")

  result = acronym_collection.delete_one({'guild_id': guild_id, 'phrase': normalized})
  return result.deleted_count > 0