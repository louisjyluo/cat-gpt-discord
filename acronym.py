import json
import os


acronym_map = {}


def load_acronym_database():
  global acronym_map
  try:
    if os.path.exists("./databases/acronyms.json"):
      with open("./databases/acronyms.json", "r") as file:
        acronym_map = json.load(file)
  except Exception as e:
    print(f"Error loading acronym database: {e}")


def save_acronym_database():
  try:
    with open("./databases/acronyms.json", "w") as file:
      json.dump(acronym_map, file)
  except Exception as e:
    print(f"Error saving acronym database: {e}")


def acronym(phrase):
  if len(phrase.split()) == 1:
    return word_acronym(phrase)
  return phrase_acronym(phrase)


def word_acronym(word):
  generated_acronym = word[-(len(word) // 2):].upper()
  acronym_map[word] = generated_acronym
  return generated_acronym


def phrase_acronym(phrase):
  generated_acronym = ""
  for word in phrase.split():
    if word[0].isalpha():
      generated_acronym += word[0].upper()
  acronym_map[phrase.lower().strip()] = generated_acronym
  return generated_acronym


def get_matching_acronym(content_lower):
  matched_phrase = next(
    (phrase for phrase in sorted(acronym_map.keys(), key=len, reverse=True) if phrase in content_lower),
    None
  )
  if matched_phrase:
    return acronym_map[matched_phrase]
  return None