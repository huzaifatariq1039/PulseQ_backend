"""Performance monitoring middleware for API request/response timing"""
import time
import logging
from typing import Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("performance")

# Thread-safe request context storage
_request_timings: Dict[str, Dict[str, float]] = {}


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware to track API response times and log slow endpoints"""
    
    SLOW_THRESHOLD_MS = 300  # Log warnings for endpoints slower than 300ms
    VERY_SLOW_THRESHOLD_MS = 1000  # Log errors for endpoints slower than 1s
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        request_id = f"{request.method}:{request.url.path}"
        
        # Initialize timing context
        _request_timings[request_id] = {
            "start": start_time,
            "db_queries": 0,
            "db_time_ms": 0.0,
        }
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate total time
            total_time_ms = (time.time() - start_time) * 1000
            
            # Get DB query time from context
            db_time_ms = _request_timings.get(request_id, {}).get("db_time_ms", 0.0)
            db_queries = _request_timings.get(request_id, {}).get("db_queries", 0)
            
            # Calculate other times
            serialization_time_ms = total_time_ms - db_time_ms
            
            # Log performance metrics
            log_entry = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "total_ms": round(total_time_ms, 2),
                "db_query_ms": round(db_time_ms, 2),
                "db_queries": db_queries,
                "serialization_ms": round(serialization_time_ms, 2),
                "query_params": dict(request.query_params) if request.query_params else None,
            }
            
            # Log based on performance thresholds
            if total_time_ms >= self.VERY_SLOW_THRESHOLD_MS:
                logger.error(f"🔴 VERY SLOW API: {log_entry}")
            elif total_time_ms >= self.SLOW_THRESHOLD_MS:
                logger.warning(f"🟡 SLOW API: {log_entry}")
            else:
                logger.info(f"🟢 API: {log_entry}")
            
            # Add timing header to response (for debugging)
            response.headers["X-Response-Time-ms"] = f"{total_time_ms:.2f}"
            response.headers["X-DB-Time-ms"] = f"{db_time_ms:.2f}"
            
            return response
            
        except Exception as e:
            total_time_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ API ERROR: {request.method} {request.url.path} - {total_time_ms:.2f}ms - {str(e)}")
            raise
        finally:
            # Cleanup timing context
            _request_timings.pop(request_id, None)


def track_db_query(duration_ms: float):
    """Track individual database query time (called from SQLAlchemy event listeners)"""
    # This function will be called from database.py event listeners
    # For now, we'll implement it in database.py directly
    pass


def get_performance_summary() -> Dict[str, Any]:
    """Get performance summary for monitoring dashboard"""
    return {
        "slow_threshold_ms": PerformanceMiddleware.SLOW_THRESHOLD_MS,
        "very_slow_threshold_ms": PerformanceMiddleware.VERY_SLOW_THRESHOLD_MS,
        "active_requests": len(_request_timings),
    }
