"""
Centralized caching service with Redis compatibility
Supports both in-memory caching (development) and Redis (production)
"""
import json
import logging
from typing import Optional, Any, Dict
from time import time
from functools import wraps

logger = logging.getLogger("performance.cache")

# In-memory cache store (fallback for development)
_cache_store: Dict[str, tuple[float, Any]] = {}

# Redis client (optional - set when Redis is available)
_redis_client = None


def init_redis(host: str = "localhost", port: int = 6379, db: int = 0, password: str = None):
    """Initialize Redis connection for production caching"""
    global _redis_client
    try:
        import redis
        _redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=True
        )
        # Test connection
        _redis_client.ping()
        logger.info("✅ Redis cache initialized successfully")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Redis not available, using in-memory cache: {e}")
        _redis_client = None
        return False


class CacheService:
    """
    Unified caching service with TTL support
    Automatically uses Redis if available, falls back to in-memory cache
    """
    
    # TTL Constants
    TTL_SHORT = 60        # 1 minute
    TTL_DEFAULT = 300     # 5 minutes
    TTL_LONG = 1800       # 30 minutes
    TTL_STATIC = 3600     # 1 hour
    TTL_VERY_LONG = 86400 # 24 hours
    
    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Get cached value by key"""
        try:
            # Try Redis first if available
            if _redis_client:
                data = _redis_client.get(key)
                if data:
                    logger.debug(f"Cache HIT (Redis): {key}")
                    return json.loads(data)
                logger.debug(f"Cache MISS (Redis): {key}")
                return None
            
            # Fallback to in-memory cache
            exp, val = _cache_store.get(key, (0.0, None))
            if exp >= time():
                logger.debug(f"Cache HIT (memory): {key}")
                return val
            
            # Expired
            _cache_store.pop(key, None)
            logger.debug(f"Cache EXPIRED (memory): {key}")
            return None
            
        except Exception as e:
            logger.error(f"Cache GET error for {key}: {e}")
            return None
    
    @classmethod
    def set(cls, key: str, value: Any, ttl: int = TTL_DEFAULT) -> bool:
        """Set cached value with TTL"""
        try:
            # Try Redis first
            if _redis_client:
                _redis_client.setex(key, ttl, json.dumps(value))
                logger.debug(f"Cache SET (Redis): {key} (TTL: {ttl}s)")
                return True
            
            # Fallback to in-memory cache
            _cache_store[key] = (time() + ttl, value)
            logger.debug(f"Cache SET (memory): {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Cache SET error for {key}: {e}")
            return False
    
    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete cached value"""
        try:
            if _redis_client:
                _redis_client.delete(key)
                return True
            
            _cache_store.pop(key, None)
            return True
        except Exception as e:
            logger.error(f"Cache DELETE error for {key}: {e}")
            return False
    
    @classmethod
    def invalidate_prefix(cls, prefix: str) -> int:
        """Invalidate all cache keys starting with prefix"""
        removed = 0
        try:
            if _redis_client:
                # Redis doesn't support prefix deletion natively, use SCAN
                cursor = 0
                while True:
                    cursor, keys = _redis_client.scan(cursor, match=f"{prefix}*", count=100)
                    if keys:
                        removed += _redis_client.delete(*keys)
                    if cursor == 0:
                        break
            else:
                # In-memory cache
                for k in list(_cache_store.keys()):
                    if k.startswith(prefix):
                        del _cache_store[k]
                        removed += 1
            
            if removed > 0:
                logger.info(f"Cache invalidated {removed} keys with prefix: {prefix}")
            return removed
            
        except Exception as e:
            logger.error(f"Cache invalidation error for prefix {prefix}: {e}")
            return 0
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            if _redis_client:
                info = _redis_client.info()
                return {
                    "type": "redis",
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "total_keys": _redis_client.dbsize(),
                }
            else:
                return {
                    "type": "in-memory",
                    "total_keys": len(_cache_store),
                    "active_keys": sum(1 for exp, _ in _cache_store.values() if exp >= time()),
                }
        except Exception as e:
            return {"error": str(e)}


# Convenience functions for direct use
def cache_get(key: str) -> Optional[Any]:
    """Get value from cache"""
    return CacheService.get(key)


def cache_set(key: str, value: Any, ttl: int = CacheService.TTL_DEFAULT) -> bool:
    """Set value in cache"""
    return CacheService.set(key, value, ttl)


def cache_delete(key: str) -> bool:
    """Delete value from cache"""
    return CacheService.delete(key)


def cache_invalidate_prefix(prefix: str) -> int:
    """Invalidate cache keys by prefix"""
    return CacheService.invalidate_prefix(prefix)


def cached(ttl: int = CacheService.TTL_DEFAULT, key_prefix: str = ""):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            key_args = "_".join(str(a) for a in args[:3])  # First 3 args
            cache_key = f"{key_prefix}{func.__name__}:{key_args}"
            
            # Try cache
            cached_result = CacheService.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache HIT for {func.__name__}")
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            CacheService.set(cache_key, result, ttl)
            logger.debug(f"Cache SET for {func.__name__} (TTL: {ttl}s)")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            key_args = "_".join(str(a) for a in args[:3])
            cache_key = f"{key_prefix}{func.__name__}:{key_args}"
            
            # Try cache
            cached_result = CacheService.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache HIT for {func.__name__}")
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            CacheService.set(cache_key, result, ttl)
            logger.debug(f"Cache SET for {func.__name__} (TTL: {ttl}s)")
            
            return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
