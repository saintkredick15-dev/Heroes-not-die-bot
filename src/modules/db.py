import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("../.env")

def get_database():
    mongo_url = os.getenv("MONGO_DB")
    if not mongo_url:
        raise ValueError("MONGO_DB not found in .env file")
    
    client = AsyncIOMotorClient(mongo_url)
    return client.discord_bot