"""Performance timing utilities for endpoints"""
import time
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("performance.endpoints")


def timed_endpoint(func: Callable) -> Callable:
    """Decorator to track endpoint execution time and log slow endpoints"""
    
    SLOW_THRESHOLD_MS = 300
    
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms >= SLOW_THRESHOLD_MS:
                logger.warning(
                    f"⚠️ Slow endpoint: {func.__name__} took {elapsed_ms:.2f}ms"
                )
            
            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"❌ Endpoint error: {func.__name__} after {elapsed_ms:.2f}ms - {str(e)}"
            )
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms >= SLOW_THRESHOLD_MS:
                logger.warning(
                    f"⚠️ Slow endpoint: {func.__name__} took {elapsed_ms:.2f}ms"
                )
            
            return result
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"❌ Endpoint error: {func.__name__} after {elapsed_ms:.2f}ms - {str(e)}"
            )
            raise
    
    # Return appropriate wrapper based on function type
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def track_execution_time(label: str = "Operation"):
    """Context manager to track execution time of code blocks"""
    import time
    from contextlib import contextmanager
    
    @contextmanager
    def timer():
        start = time.time()
        try:
            yield
        finally:
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= 100:  # Log if over 100ms
                logger.info(f"⏱️ {label} took {elapsed_ms:.2f}ms")
    
    return timer()
