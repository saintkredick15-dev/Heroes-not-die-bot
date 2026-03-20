import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def main():
    client = AsyncIOMotorClient(os.getenv('MONGO_DB'))
    db = client.discord_bot
    docs = await db.guild_settings.find().to_list(100)
    for doc in docs:
        eco = doc.get("economy", {})
        if "currency_emoji" in eco and eco["currency_emoji"] in ["💲", "🪙", "$"]:
            print(f"Fixing guild {doc['_id']} from {eco['currency_emoji']}")
            eco["currency_emoji"] = "<:coin:1478487028105482485>"
            await db.guild_settings.update_one(
                {"_id": doc["_id"]},
                {"$set": {"economy": eco}}
            )

if __name__ == '__main__':
    asyncio.run(main())
