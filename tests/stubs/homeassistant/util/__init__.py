"""Stub for homeassistant.util (Throttle)."""
from functools import wraps


def Throttle(min_time):
    """Decorator that disables throttling for tests (always calls through)."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
