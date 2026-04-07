from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')
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
