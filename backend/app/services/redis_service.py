"""Async Redis service for Upstash serverless Redis with Pub/Sub support.

Provides:
- Async Redis client configured with SSL/TLS (rediss://)
- Channel subscriptions for distributed WebSocket broadcasting
- Connection pooling and automatic reconnection
"""

import redis.asyncio as redis
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.client import PubSub
import logging
from typing import Optional, Callable, Any

from app.config import REDIS_URL, REDIS_SOCKET_TIMEOUT, REDIS_SOCKET_CONNECT_TIMEOUT
from app.logger import get_logger

logger = get_logger(__name__)


class RedisService:
    """Async Redis client service for Upstash serverless Redis."""

    def __init__(self):
        self.client: Optional[Redis] = None
        self.pubsub: Optional[PubSub] = None

    async def connect(self) -> Redis:
        """Initialize async Redis connection pool with SSL/TLS support.

        REDIS_URL should be in format:
        - redis://[:password]@host:port[/db]
        - rediss://[:password]@host:port[/db]  (SSL/TLS)

        Upstash example: rediss://:token@host.upstash.io:port
        """
        if self.client is not None:
            return self.client

        if not REDIS_URL:
            logger.warning("REDIS_URL not configured. Redis Pub/Sub disabled.")
            return None

        try:
            # Parse URL and auto-detect SSL from rediss:// scheme
            self.client = await redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                # Connection pool settings for distributed/serverless usage
                max_connections=10,
                retry_on_timeout=True,
            )
            # Test connection
            await self.client.ping()
            logger.info("✅ Redis client connected successfully (Upstash)")
            return self.client
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.client = None
            raise

    async def close(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Redis client closed")

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis channel.

        Args:
            channel: Channel name (e.g., 'room:123')
            message: JSON string message

        Returns:
            Number of subscribers that received the message
        """
        if not self.client:
            logger.warning(f"Redis not connected; message to '{channel}' not published")
            return 0

        try:
            subscribers = await self.client.publish(channel, message)
            return subscribers
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")
            raise

    async def subscribe(self, *channels: str) -> PubSub:
        """Subscribe to one or more Redis channels.

        Args:
            *channels: Channel names to subscribe to

        Returns:
            PubSub object for receiving messages
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        try:
            pubsub = self.client.pubsub()
            await pubsub.subscribe(*channels)
            logger.info(f"Subscribed to channels: {channels}")
            return pubsub
        except Exception as e:
            logger.error(f"Failed to subscribe to {channels}: {e}")
            raise

    async def unsubscribe(self, pubsub: PubSub, *channels: str):
        """Unsubscribe from channels.

        Args:
            pubsub: PubSub object
            *channels: Channel names to unsubscribe from
        """
        if pubsub:
            try:
                await pubsub.unsubscribe(*channels)
                logger.info(f"Unsubscribed from channels: {channels}")
            except Exception as e:
                logger.error(f"Failed to unsubscribe from {channels}: {e}")

    async def close_pubsub(self, pubsub: PubSub):
        """Close a PubSub connection."""
        if pubsub:
            try:
                await pubsub.close()
            except Exception as e:
                logger.error(f"Error closing PubSub: {e}")


# Global singleton instance
_redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    """Get or create the global Redis service instance."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service


async def init_redis():
    """Initialize Redis connection (call from app startup)."""
    service = get_redis_service()
    try:
        await service.connect()
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")


async def close_redis():
    """Close Redis connection (call from app shutdown)."""
    service = get_redis_service()
    await service.close()
