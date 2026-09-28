from db import acronym_collection, banned_phrase_collection
import random


def normalize_reserved_acronym(value):
  return "".join(char for char in value.upper() if char.isalnum())


def validate_generated_acronym(generated_acronym, reserved_acronyms=None):
  normalized = normalize_reserved_acronym(generated_acronym)
  if reserved_acronyms and normalized in reserved_acronyms:
    raise ValueError(f"You can't create the command **{generated_acronym}** as an acronym.")

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


def acronym(guild_id, phrase, author_id=None, reserved_acronyms=None):
  guild_id = str(guild_id)
  normalized = phrase.strip()
  if len(normalized.replace(" ", "")) < 4:
    raise ValueError("Phrase must be at least 4 characters long.")
  if is_phrase_banned(guild_id, phrase):
    raise ValueError(f"The phrase **{normalized.lower()}** is banned and can't be acro'd.")
  if len(phrase.split()) == 1:
    return word_acronym(guild_id, phrase, author_id, reserved_acronyms)
  return phrase_acronym(guild_id, phrase, author_id, reserved_acronyms)


def word_acronym(guild_id, word, author_id=None, reserved_acronyms=None):
  normalized = word.strip()
  if len(normalized) < 4:
    raise ValueError("Word must be at least 4 characters long.")

  generated_acronym = word[-(len(word) // 2):].upper()
  validate_generated_acronym(generated_acronym, reserved_acronyms)
  existing = acronym_collection.find_one({'guild_id': guild_id, 'phrase': word.lower().strip()})
  if existing:
    raise ValueError(f"This acronym has already been added: **{existing['phrase']}** → {existing['acronym']}")
  doc = {'guild_id': guild_id, 'phrase': word.lower().strip(), 'acronym': generated_acronym}
  if author_id is not None:
    doc['author_id'] = str(author_id)
  acronym_collection.insert_one(doc)
  return generated_acronym


def phrase_acronym(guild_id, phrase, author_id=None, reserved_acronyms=None):
  parts = []
  for word in phrase.split():
    i = 0
    while i < len(word) and not word[i].isalpha():
      i += 1
    prefix = word[:i]
    first_alpha = word[i].upper() if i < len(word) else ""
    parts.append(prefix + first_alpha)

  generated_acronym = "".join(parts)

  if not any(c.isalpha() for c in generated_acronym):
    raise ValueError("You can't acro a phrase of only numbers.")
  validate_generated_acronym(generated_acronym, reserved_acronyms)

  existing = acronym_collection.find_one({'guild_id': guild_id, 'phrase': phrase.lower().strip()})
  if existing:
    raise ValueError(f"This acronym has already been added: **{existing['phrase']}** → {existing['acronym']}")
  doc = {'guild_id': guild_id, 'phrase': phrase.lower().strip(), 'acronym': generated_acronym}
  if author_id is not None:
    doc['author_id'] = str(author_id)
  acronym_collection.insert_one(doc)
  return generated_acronym


def get_matching_acronym(guild_id, content_lower):
  """Find all matching acronym phrases in content and return a random one."""
  try:
    all_acronyms = list(acronym_collection.find({'guild_id': str(guild_id)}))
    matches = [entry['acronym'] for entry in all_acronyms if entry['phrase'] in content_lower]
    if not matches:
      return None
    return random.choice(matches)
  except Exception as e:
    print(f"Error getting matching acronym: {e}")
    return None


def check_unacro_permission(doc, requester_id, blouis_id):
  requester_id = str(requester_id)
  if requester_id == str(blouis_id):
    return
  author_id = doc.get('author_id')
  if not author_id:
    raise ValueError("Can't unacro unclaimed acronyms")
  if requester_id != str(author_id):
    raise ValueError("Only the person who claimed this acronym can remove it.")


def unacronym(guild_id, phrase, requester_id, blouis_id):
  guild_id = str(guild_id)
  normalized = phrase.strip().lower()
  if not normalized:
    raise ValueError("Word or phrase cannot be empty.")

  doc = acronym_collection.find_one({'guild_id': guild_id, 'phrase': normalized})
  if not doc:
    return False

  check_unacro_permission(doc, requester_id, blouis_id)

  result = acronym_collection.delete_one({'_id': doc['_id']})
  return result.deleted_count > 0


def unacronym_by_acronym(guild_id, acronym_str, requester_id, blouis_id):
  guild_id = str(guild_id)
  normalized = acronym_str.strip().upper()
  if not normalized:
    raise ValueError("Acronym cannot be empty.")

  doc = acronym_collection.find_one({'guild_id': guild_id, 'acronym': normalized})
  if not doc:
    return False

  check_unacro_permission(doc, requester_id, blouis_id)

  result = acronym_collection.delete_one({'_id': doc['_id']})
  return result.deleted_count > 0


def unacronym_all_by_author(guild_id, author_id):
  guild_id = str(guild_id)
  normalized_author_id = str(author_id).strip()
  if not normalized_author_id:
    raise ValueError("Author ID cannot be empty.")

  result = acronym_collection.delete_many({'guild_id': guild_id, 'author_id': normalized_author_id})
  return result.deleted_count


def is_phrase_banned(guild_id, phrase):
  guild_id = str(guild_id)
  normalized = phrase.strip().lower()
  return banned_phrase_collection.find_one({'guild_id': guild_id, 'phrase': normalized}) is not None


def ban_phrase(guild_id, phrase):
  guild_id = str(guild_id)
  normalized = phrase.strip().lower()
  if not normalized:
    raise ValueError("Phrase cannot be empty.")

  if is_phrase_banned(guild_id, normalized):
    raise ValueError(f"The phrase **{normalized}** is already banned.")

  banned_phrase_collection.insert_one({'guild_id': guild_id, 'phrase': normalized})
  existing_removed = acronym_collection.delete_one({'guild_id': guild_id, 'phrase': normalized}).deleted_count > 0
  return normalized, existing_removed


def unban_phrase(guild_id, phrase):
  guild_id = str(guild_id)
  normalized = phrase.strip().lower()
  if not normalized:
    raise ValueError("Phrase cannot be empty.")

  result = banned_phrase_collection.delete_one({'guild_id': guild_id, 'phrase': normalized})
  return result.deleted_count > 0
