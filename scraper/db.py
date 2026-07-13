"""
MongoDB connection and operations for college data
"""
import os
from pymongo import MongoClient, UpdateOne

MONGO_URL = "mongodb+srv://anchal:anchal@anchal.hospij1.mongodb.net/dbcolleges?appName=anchal"

_client = None

def get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    return _client['dbcolleges']

def get_collection():
    return get_db()['colleges']

def upsert_college(college):
    """Insert or update a college by name + state."""
    col = get_collection()
    col.update_one(
        {'name': college['name'], 'state': college['state']},
        {'$set': college},
        upsert=True
    )

def upsert_many(colleges):
    """Bulk upsert many colleges."""
    col = get_collection()
    ops = []
    for c in colleges:
        ops.append(UpdateOne(
            {'name': c['name'], 'state': c['state']},
            {'$set': c},
            upsert=True
        ))
    if ops:
        result = col.bulk_write(ops)
        return result
    return None

def find_college(name, state):
    return get_collection().find_one({'name': name, 'state': state})

def get_all_colleges():
    return list(get_collection().find({}))

def count_colleges():
    return get_collection().count_documents({})
