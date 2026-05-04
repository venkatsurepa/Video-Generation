"""Allow running discovery as a module: python -m src.services.discovery"""

import asyncio

from .orchestrator import main

asyncio.run(main())
