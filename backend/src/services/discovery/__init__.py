"""Topic discovery service package.

Automated scanning of multiple sources to find video-worthy topics
for CrimeMill (true crime) and Street Level (travel danger narratives).

Sources:
    reddit          — r/TrueCrime, r/UnresolvedMysteries, r/travel, r/solotravel
    advisory        — US State Dept, CDC, UK FCDO travel advisories
    competitor      — YouTube competitor channel video monitoring
    court_listener  — CourtListener legal case developments
    google_trends   — Search interest spike detection
    wikipedia       — Notable crime articles and recent deaths

Usage:
    from src.services.discovery import DiscoveryOrchestrator

    orchestrator = DiscoveryOrchestrator(supabase_client, config)
    results = await orchestrator.run_all(score=True)

CLI:
    python -m src.services.discovery --score
    python -m src.services.discovery --source reddit --verbose
"""

from .advisory_poller import AdvisoryPoller
from .base import DiscoveryChannel, DiscoverySource, TopicCandidate
from .competitor_scanner import CompetitorScanner
from .court_listener import CourtListenerScanner
from .gdelt_scanner import GdeltScanner
from .google_trends import GoogleTrendsScanner
from .orchestrator import DiscoveryOrchestrator
from .reddit_scanner import RedditScanner
from .topic_scorer import TopicScorer
from .wikipedia_monitor import WikipediaMonitor

__all__ = [
    "DiscoveryOrchestrator",
    "DiscoverySource",
    "DiscoveryChannel",
    "TopicCandidate",
    "TopicScorer",
    "RedditScanner",
    "AdvisoryPoller",
    "CompetitorScanner",
    "CourtListenerScanner",
    "GdeltScanner",
    "GoogleTrendsScanner",
    "WikipediaMonitor",
]
