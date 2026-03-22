"""Rate limiting configuration using slowapi.

Tier structure:
- Heavy writes (pipeline trigger, topic discovery, analytics collect): 10/minute
- Normal writes (create video, create channel, etc.): 30/minute
- Reads: 120/minute
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Rate limit strings for consistent reuse across routers
RATE_HEAVY_WRITE = "10/minute"
RATE_NORMAL_WRITE = "30/minute"
RATE_READ = "120/minute"
RATE_ANALYTICS_COLLECT = "2/minute"
