from fastapi import Request, HTTPException, status
from typing import Dict, Optional
import time
import redis
from functools import wraps

from ..config import get_settings

settings = get_settings()


class RateLimiter:
    """
    Rate limiter using Redis for distributed rate limiting.

    Implements token bucket algorithm for flexible rate limiting.
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance (or creates new one)
        """
        if redis_client:
            self.redis = redis_client
        else:
            # Parse Redis URL
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Dict[str, any]:
        """
        Check if request is within rate limit.

        Args:
            key: Unique identifier (user ID, IP address, etc.)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Dict with rate limit status
        """
        now = time.time()
        window_key = f"rate_limit:{key}:{int(now / window_seconds)}"

        try:
            # Increment counter
            current_requests = self.redis.incr(window_key)

            # Set expiry on first request
            if current_requests == 1:
                self.redis.expire(window_key, window_seconds)

            # Check limit
            if current_requests > max_requests:
                # Get TTL for retry-after
                ttl = self.redis.ttl(window_key)

                return {
                    'allowed': False,
                    'current': current_requests,
                    'limit': max_requests,
                    'retry_after': ttl if ttl > 0 else window_seconds
                }

            return {
                'allowed': True,
                'current': current_requests,
                'limit': max_requests,
                'remaining': max_requests - current_requests
            }

        except Exception as e:
            # If Redis fails, allow request (fail open)
            print(f"Rate limit check failed: {e}")
            return {
                'allowed': True,
                'error': str(e)
            }

    def check_rate_limit_sliding(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Dict[str, any]:
        """
        Check rate limit using sliding window algorithm.

        More accurate than fixed window but slightly more expensive.

        Args:
            key: Unique identifier
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Dict with rate limit status
        """
        now = time.time()
        window_start = now - window_seconds
        key_name = f"rate_limit:sliding:{key}"

        try:
            pipe = self.redis.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key_name, 0, window_start)

            # Count requests in window
            pipe.zcard(key_name)

            # Add current request
            pipe.zadd(key_name, {str(now): now})

            # Set expiry
            pipe.expire(key_name, window_seconds)

            results = pipe.execute()
            current_requests = results[1]

            if current_requests >= max_requests:
                # Get oldest request time
                oldest = self.redis.zrange(key_name, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    retry_after = int(oldest_time + window_seconds - now)
                else:
                    retry_after = window_seconds

                return {
                    'allowed': False,
                    'current': current_requests + 1,
                    'limit': max_requests,
                    'retry_after': max(1, retry_after)
                }

            return {
                'allowed': True,
                'current': current_requests + 1,
                'limit': max_requests,
                'remaining': max_requests - current_requests - 1
            }

        except Exception as e:
            # Fail open
            print(f"Rate limit check failed: {e}")
            return {
                'allowed': True,
                'error': str(e)
            }


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 100, window_seconds: int = 60, use_sliding: bool = False):
    """
    Decorator for rate limiting endpoints.

    Usage:
        @router.get("/api/endpoint")
        @rate_limit(max_requests=10, window_seconds=60)
        async def endpoint(request: Request):
            ...

    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        use_sliding: Use sliding window (more accurate)

    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get identifier (user ID or IP address)
            user_id = getattr(request.state, 'user_id', None)

            if user_id:
                key = f"user:{user_id}"
            else:
                # Use IP address for unauthenticated requests
                client_ip = request.client.host
                key = f"ip:{client_ip}"

            # Check rate limit
            if use_sliding:
                result = rate_limiter.check_rate_limit_sliding(key, max_requests, window_seconds)
            else:
                result = rate_limiter.check_rate_limit(key, max_requests, window_seconds)

            if not result['allowed']:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        'error': 'Rate limit exceeded',
                        'limit': result['limit'],
                        'retry_after': result['retry_after']
                    },
                    headers={
                        'Retry-After': str(result['retry_after']),
                        'X-RateLimit-Limit': str(result['limit']),
                        'X-RateLimit-Remaining': '0'
                    }
                )

            # Add rate limit headers to response
            response = await func(request, *args, **kwargs)

            # Add headers if response supports it
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(result['limit'])
                response.headers['X-RateLimit-Remaining'] = str(result.get('remaining', 0))

            return response

        return wrapper

    return decorator


async def rate_limit_middleware(request: Request, call_next):
    """
    Global rate limit middleware.

    Applies rate limiting to all requests.

    Args:
        request: FastAPI request
        call_next: Next middleware

    Returns:
        Response
    """
    # Get user ID from JWT if authenticated
    user_id = None
    if hasattr(request.state, 'user'):
        user_id = request.state.user.id

    # Build rate limit key
    if user_id:
        key = f"global:user:{user_id}"
        max_requests = 1000  # 1000 requests per minute for authenticated users
    else:
        client_ip = request.client.host
        key = f"global:ip:{client_ip}"
        max_requests = 100  # 100 requests per minute for unauthenticated

    # Check rate limit
    result = rate_limiter.check_rate_limit(key, max_requests, 60)

    if not result['allowed']:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                'error': 'Too many requests',
                'retry_after': result['retry_after']
            },
            headers={'Retry-After': str(result['retry_after'])}
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers
    response.headers['X-RateLimit-Limit'] = str(result['limit'])
    response.headers['X-RateLimit-Remaining'] = str(result.get('remaining', 0))

    return response
