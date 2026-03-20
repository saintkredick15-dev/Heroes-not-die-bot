import time
import asyncio
from typing import Any, Dict, Optional, Tuple

class LRUCache:
    
    def __init__(self, capacity: int = 1000, ttl_seconds: int = 60):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        
        self.cache: Dict[str, Tuple[Any, float]] = {} 
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        
        async with self.lock:
            if key not in self.cache:
                return None
            
            value, timestamp = self.cache[key]
            
            if time.time() - timestamp > self.ttl_seconds:
                del self.cache[key]
                return None
            
            del self.cache[key]
            self.cache[key] = (value, timestamp)
            return value

    async def set(self, key: str, value: Any):
        
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
            elif len(self.cache) >= self.capacity:
                
                first_key = next(iter(self.cache))
                del self.cache[first_key]
                
            self.cache[key] = (value, time.time())
            
    async def invalidate(self, key: str):
        
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                
    async def clear(self):
        
        async with self.lock:
            self.cache.clear()

guild_settings_cache = LRUCache(capacity=500, ttl_seconds=60)
user_data_cache = LRUCache(capacity=2000, ttl_seconds=30)
