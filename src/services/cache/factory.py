import logging

import redis
from src.config import Settings
from src.services.cache.client import CacheClient

logger = logging.getLogger(__name__)


def make_redis_client(settings: Settings) -> redis.Redis:
    """Create a lazy Redis client; connectivity is checked outside startup."""
    redis_settings = settings.redis

    try:
        client = redis.Redis(
            host=redis_settings.host,
            port=redis_settings.port,
            password=redis_settings.password if redis_settings.password else None,
            db=redis_settings.db,
            decode_responses=redis_settings.decode_responses,
            socket_timeout=redis_settings.socket_timeout,
            socket_connect_timeout=redis_settings.socket_connect_timeout,
            retry_on_timeout=False,
            ssl=redis_settings.ssl,
            ssl_ca_certs=redis_settings.ssl_ca_certs,
            ssl_cert_reqs=redis_settings.ssl_cert_reqs if redis_settings.ssl else None,
        )

        logger.info("Redis cache client configured for %s:%s", redis_settings.host, redis_settings.port)
        return client

    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating Redis client: {e}")
        raise


def make_cache_client(settings: Settings) -> CacheClient | None:
    """Create the optional cache without making API startup depend on Redis."""
    try:
        redis_client = make_redis_client(settings)
        cache_client = CacheClient(redis_client, settings.redis)
        logger.info("Exact match cache client created successfully")
        return cache_client
    except Exception as e:
        logger.warning("Redis cache disabled after construction failure: %s", type(e).__name__)
        return None
