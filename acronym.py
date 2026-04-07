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


def acronym(phrase):
  if len(phrase.split()) == 1:
    return word_acronym(phrase)
  return phrase_acronym(phrase)


def word_acronym(word):
  generated_acronym = word[-(len(word) // 2):].upper()
  # Upsert: update if exists, insert if not
  acronym_collection.update_one(
    {'phrase': word},
    {'$set': {'acronym': generated_acronym}},
    upsert=True
  )
  return generated_acronym


def phrase_acronym(phrase):
  generated_acronym = ""
  for word in phrase.split():
    if word[0].isalpha():
      generated_acronym += word[0].upper()
  
  # Upsert: update if exists, insert if not
  acronym_collection.update_one(
    {'phrase': phrase.lower().strip()},
    {'$set': {'acronym': generated_acronym}},
    upsert=True
  )
  return generated_acronym


def get_matching_acronym(content_lower):
  """Find the longest matching acronym phrase in content."""
  try:
    # Get all acronyms and sort by phrase length (longest first)
    all_acronyms = list(acronym_collection.find({}))
    all_acronyms.sort(key=lambda x: len(x['phrase']), reverse=True)
    
    for entry in all_acronyms:
      if entry['phrase'] in content_lower:
        return entry['acronym']
    
    return None
  except Exception as e:
    print(f"Error getting matching acronym: {e}")
    return None