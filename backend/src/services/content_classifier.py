"""Content classifier — YouTube self-certification & ad-suitability prediction.

Evaluates scripts, titles, thumbnails, and opening narration against YouTube's
14 advertiser-unfriendly categories and generates honest self-certification
answers for the upload questionnaire.

Uses Claude Haiku 4.5 (cheapest structured-output model) for text analysis
and Claude's vision capability for thumbnail classification.

Key principles from the project bible:
- Rate HONESTLY: short-term yellow builds long-term trust score.
- After ~20 honest ratings YouTube trusts your self-cert over its own classifiers.
- Financial-crime documentaries qualify for EDSA exception (Educational/Documentary).
- Opening 7-8 seconds weighted most heavily by YouTube's classifier.
- Profanity in titles = near-certain zero revenue.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import anthropic
import structlog

from src.models.content_safety import (
    CategoryRating,
    ContentClassification,
    First30sCheck,
    FlaggedTerm,
    SelfCertAnswers,
    ThumbnailClassification,
    TitleSafetyCheck,
)

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Model routing & pricing
# ---------------------------------------------------------------------------

MODEL_HAIKU: str = "claude-haiku-4-5-20251001"

PRICING: dict[str, dict[str, Decimal]] = {
    MODEL_HAIKU: {"input": Decimal("1"), "output": Decimal("5")},
}
_ONE_MILLION = Decimal("1_000_000")

MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 1.0


# ---------------------------------------------------------------------------
# YouTube's 14 advertiser-unfriendly categories
# ---------------------------------------------------------------------------

CATEGORIES: list[str] = [
    "inappropriate_language",
    "violence",
    "adult_content",
    "shocking",
    "harmful_acts",
    "hateful",
    "drugs",
    "firearms",
    "controversial_issues",
    "sensitive_events",
    "dishonest_behavior",
    "family_inappropriate",
    "incendiary",
    "tobacco",
]

CATEGORY_LABELS: dict[str, str] = {
    "inappropriate_language": "Inappropriate language (profanity, slurs)",
    "violence": "Violence (graphic depictions, glorification)",
    "adult_content": "Adult/sexual content",
    "shocking": "Shocking content (disturbing imagery/descriptions)",
    "harmful_acts": "Harmful or dangerous acts",
    "hateful": "Hateful content",
    "drugs": "Recreational drugs and drug-related content",
    "firearms": "Firearms-related content",
    "controversial_issues": "Controversial issues and sensitive events",
    "sensitive_events": "Sensitive events (active incidents, tragedies)",
    "dishonest_behavior": "Enabling dishonest behavior (scams, fraud HOW-TOs)",
    "family_inappropriate": "Content inappropriate for families",
    "incendiary": "Incendiary and demeaning content",
    "tobacco": "Tobacco-related content",
}


# ---------------------------------------------------------------------------
# Title-level demonetisation triggers
# ---------------------------------------------------------------------------

# Sourced from Nerd City / Hoopoz research — a compact subset of the most
# impactful trigger words.  The full Hoopoz list has 16,574 entries; we focus
# on the terms most relevant to crime documentary content.

TITLE_TRIGGER_WORDS: set[str] = {
    # Violence
    "kill",
    "killed",
    "killing",
    "murder",
    "murdered",
    "murderer",
    "homicide",
    "manslaughter",
    "assassinate",
    "assassinated",
    "assault",
    "assaulted",
    "shooting",
    "shot",
    "stabbing",
    "stabbed",
    "execution",
    "executed",
    "massacre",
    "slaughter",
    "slaughtered",
    "suicide",
    "suicidal",
    # Profanity (any f-word variant = zero revenue)
    "fuck",
    "fucking",
    "fucked",
    "fucker",
    "shit",
    "bullshit",
    "bitch",
    "ass",
    "damn",
    "hell",
    "crap",
    # Sexual
    "sex",
    "sexual",
    "rape",
    "raped",
    "rapist",
    "molest",
    "molested",
    "pedophile",
    "paedophile",
    # Drugs
    "cocaine",
    "heroin",
    "meth",
    "methamphetamine",
    "fentanyl",
    "overdose",
    "overdosed",
    # Sensitive
    "terrorist",
    "terrorism",
    "bomb",
    "bombing",
    "bomber",
    "genocide",
    "holocaust",
    # Surprisingly flagged (from Nerd City study)
    "dead",
    "death",
    "die",
    "died",
    "dying",
    "corpse",
    "body",
    "victim",
    "abuse",
    "abused",
    "gun",
    "weapon",
}

# Safe alternatives for common trigger words in titles
TITLE_SAFE_ALTERNATIVES: dict[str, str] = {
    "kill": "took the life of",
    "killed": "lost their life",
    "killing": "taking lives",
    "murder": "the case of",
    "murdered": "found deceased",
    "suicide": "tragic end",
    "dead": "gone",
    "death": "the end",
    "die": "perish",
    "died": "passed away",
    "shot": "targeted",
    "shooting": "incident",
    "assault": "attack",
    "rape": "the crime",
    "victim": "survivor",
    "abuse": "mistreatment",
    "gun": "weapon",
    "bomb": "device",
    "corpse": "remains",
    "body": "remains",
    "terrorist": "extremist",
    "overdose": "substance incident",
}


# ---------------------------------------------------------------------------
# Opening narration — forbidden words and coded-language mapping
# ---------------------------------------------------------------------------

OPENING_FORBIDDEN: set[str] = {
    "kill",
    "killed",
    "killing",
    "murder",
    "murdered",
    "suicide",
    "assault",
    "assaulted",
    "shooting",
    "shot",
}

CODED_LANGUAGE: dict[str, str] = {
    "kill": "took their life",
    "killed": "lost their life",
    "murder": "was found deceased",
    "murdered": "was found deceased",
    "suicide": "took their own life",
    "assault": "was attacked",
    "assaulted": "was attacked",
    "shooting": "was targeted",
    "shot": "was targeted",
}


# ---------------------------------------------------------------------------
# Classification system prompt
# ---------------------------------------------------------------------------

CLASSIFIER_SYSTEM_PROMPT: str = """\
You are a YouTube content-policy expert specializing in ad-suitability \
classification for crime documentary channels.

Your task is to classify a script against YouTube's 14 advertiser-unfriendly \
categories and determine self-certification ratings.

## YouTube's 14 Categories

For each category, rate as:
- "none": No flags at all.
- "mild": Minor references in an educational/documentary context.
- "moderate": Descriptive content with educational framing — yellow-icon risk.
- "severe": Graphic, glorifying, or instructional content — red icon likely.

Categories:
1. inappropriate_language — Profanity, slurs, derogatory language
2. violence — Graphic depictions or glorification of violence
3. adult_content — Sexual content, nudity
4. shocking — Disturbing imagery or descriptions
5. harmful_acts — Dangerous activities that could be imitated
6. hateful — Content targeting protected groups
7. drugs — Recreational drug use, drug-related content
8. firearms — Firearms-related content
9. controversial_issues — Politically divisive, controversial topics
10. sensitive_events — Active incidents, recent tragedies
11. dishonest_behavior — Scam/fraud HOW-TOs (NOT documentaries ABOUT crime)
12. family_inappropriate — Not suitable for family audiences
13. incendiary — Content meant to demean or inflame
14. tobacco — Tobacco product promotion or use

## EDSA Exception

YouTube grants an exception for Educational, Documentary, Scientific, and \
Artistic content.  Crime documentaries that REPORT on crime WITHOUT \
glorifying, instructing, or sensationalizing it are eligible.

Key distinction: "This is how the Ponzi scheme defrauded investors" \
(documentary) vs "Here's how to run a Ponzi scheme" (instructional).

## Financial Crime Context

Financial crime documentaries TYPICALLY score:
- Violence: "none" (financial crime is non-violent)
- Controversial issues: "mild" to "moderate" (fraud is newsworthy)
- Dishonest behavior: "none" (documenting crime ≠ teaching crime)
- YouTube EXPLICITLY lists documentaries about crime as eligible for full ads

## Output Format

Respond with ONLY a JSON object (no markdown fences, no explanation):

{
  "categories": {
    "inappropriate_language": {
      "severity": "none|mild|moderate|severe",
      "confidence": 0.0-1.0,
      "reasoning": "brief explanation",
      "edsa_mitigated": false
    },
    ... (all 14 categories)
  },
  "overall_risk": "low|medium|high",
  "edsa_eligible": true,
  "edsa_reasoning": "why EDSA applies or doesn't",
  "flagged_terms": [
    {
      "term": "word",
      "location": "title|first_30_seconds|script_body|description",
      "category": "category_name",
      "severity": "none|mild|moderate|severe",
      "safe_alternative": "suggested replacement or null"
    }
  ],
  "suggested_fixes": ["list of specific actionable changes to improve ad-suitability"]
}
"""


THUMBNAIL_SYSTEM_PROMPT: str = """\
You are a YouTube thumbnail policy expert.  Analyse the provided thumbnail \
image for content that could trigger demonetisation or policy violations.

YouTube scans thumbnails INDEPENDENTLY from video content.  A graphic \
thumbnail can trigger demonetisation even if the video is completely clean.

Check for:
1. Graphic imagery (blood, gore, weapons, violence)
2. Misleading content (clickbait that doesn't match video content)
3. Sexually suggestive elements
4. Shocking or disturbing imagery
5. Text containing profanity or trigger words

Respond with ONLY a JSON object:

{
  "is_safe": true|false,
  "overall_risk": "low|medium|high",
  "flags": ["list of specific issues found"],
  "reasoning": "brief overall assessment"
}
"""


FIRST_30S_SYSTEM_PROMPT: str = """\
You are a YouTube content-policy expert.  Analyse the first ~30 seconds of \
narration for a crime documentary.

YouTube's classifier weights the FIRST 7-8 SECONDS most heavily.  Forbidden \
words in the opening can trigger automatic demonetisation regardless of the \
rest of the video.

Check for:
1. Forbidden words: kill, murder, suicide, assault, shooting, dead, death
2. Profanity of ANY kind (auto-demonetises in opening)
3. Graphic descriptions of violence or death
4. Coded-language violations (should use "lost their life" instead of "killed")

For each flagged term, provide the safe alternative from the coded-language \
glossary.

Respond with ONLY a JSON object:

{
  "passed": true|false,
  "flagged_terms": [
    {
      "term": "the word",
      "location": "first_30_seconds",
      "category": "category_name",
      "severity": "mild|moderate|severe",
      "safe_alternative": "replacement"
    }
  ],
  "coded_language_violations": ["list of terms that should use coded language"],
  "recommendations": ["specific actionable fixes"]
}
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ContentClassifierError(Exception):
    """Base error for content classification failures."""


class ClassifierRateLimitError(ContentClassifierError):
    """Anthropic rate-limit hit after retries exhausted."""


class ClassifierAPIError(ContentClassifierError):
    """Non-retryable API error from Anthropic."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> Decimal:
    """Return USD cost for a single API call."""
    prices = PRICING.get(model)
    if prices is None:
        return Decimal("0")
    billable_input = input_tokens - cached_input_tokens
    cached_cost = Decimal(cached_input_tokens) * prices["input"] * Decimal("0.1") / _ONE_MILLION
    input_cost = Decimal(billable_input) * prices["input"] / _ONE_MILLION
    output_cost = Decimal(output_tokens) * prices["output"] / _ONE_MILLION
    return (input_cost + cached_cost + output_cost).quantize(Decimal("0.000001"))


def _estimate_word_position(script: str, word_count: int) -> int:
    """Return the character index that approximately corresponds to *word_count* words."""
    idx = 0
    for count, match in enumerate(re.finditer(r"\S+", script), 1):
        if count >= word_count:
            idx = match.end()
            break
    else:
        idx = len(script)
    return idx


def _extract_first_30s(script: str) -> str:
    """Extract roughly the first 30 seconds of narration (~75 words at 150 WPM)."""
    cutoff = _estimate_word_position(script, 75)
    return script[:cutoff]


# ---------------------------------------------------------------------------
# ContentClassifier
# ---------------------------------------------------------------------------


class ContentClassifier:
    """Evaluates scripts against YouTube's 14 advertiser-unfriendly categories.

    Uses Claude Haiku 4.5 for text classification (cheapest model with
    reliable structured output) and Claude's vision capability for thumbnail
    analysis.

    Parameters
    ----------
    settings:
        Application settings — needs ``anthropic.api_key``.
    http_client:
        Shared ``httpx.AsyncClient`` (unused directly but kept for interface
        consistency with other services).
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic.api_key)

    # ------------------------------------------------------------------
    # Internal: Claude caller with retry + cost tracking
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        *,
        system_prompt: str,
        user_message: str | list[dict[str, Any]],
        max_tokens: int = 4_096,
        temperature: float = 0.0,
    ) -> tuple[str, Decimal]:
        """Send a message to Claude Haiku and return (text, cost_usd).

        Retries on transient errors with exponential back-off.
        Temperature defaults to 0 for deterministic classification.
        """
        last_exc: BaseException | None = None

        for attempt in range(MAX_RETRIES):
            t0 = time.monotonic()
            try:
                messages: list[dict[str, Any]] = (
                    [{"role": "user", "content": user_message}]
                    if isinstance(user_message, str)
                    else [{"role": "user", "content": user_message}]
                )

                response = await self._client.messages.create(
                    model=MODEL_HAIKU,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        },
                    ],
                    messages=cast("Any", messages),
                )
                latency_ms = int((time.monotonic() - t0) * 1_000)

                text: str = response.content[0].text  # type: ignore[union-attr]
                usage = response.usage
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
                cached_input = getattr(usage, "cache_creation_input_tokens", 0) + getattr(
                    usage, "cache_read_input_tokens", 0
                )
                cost = _calculate_cost(MODEL_HAIKU, input_tokens, output_tokens, cached_input)

                await logger.ainfo(
                    "classifier_claude_call",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_input,
                    cost_usd=str(cost),
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )
                return text, cost

            except anthropic.RateLimitError as exc:
                last_exc = exc
                await logger.awarning(
                    "classifier_rate_limit",
                    attempt=attempt + 1,
                    max_retries=MAX_RETRIES,
                )
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_exc = exc
                    await logger.awarning(
                        "classifier_server_error",
                        status=exc.status_code,
                        attempt=attempt + 1,
                    )
                else:
                    raise ClassifierAPIError(
                        f"Anthropic API error {exc.status_code}: {exc.message}"
                    ) from exc
            except anthropic.APIConnectionError as exc:
                last_exc = exc
                await logger.awarning(
                    "classifier_connection_error",
                    attempt=attempt + 1,
                    error=str(exc),
                )

            if attempt < MAX_RETRIES - 1:
                delay = min(BASE_RETRY_DELAY * (2**attempt), 60.0)
                await asyncio.sleep(delay)

        if isinstance(last_exc, anthropic.RateLimitError):
            raise ClassifierRateLimitError(
                f"Rate limit exceeded after {MAX_RETRIES} attempts"
            ) from last_exc
        raise ClassifierAPIError(
            f"API call failed after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # JSON parsing helper
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract a JSON object from Claude's response, tolerating markdown fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        result: dict[str, Any] = json.loads(cleaned)
        return result

    # ==================================================================
    # Public API
    # ==================================================================

    async def classify_script(
        self,
        script: str,
        title: str,
        description: str,
    ) -> ContentClassification:
        """Classify content against YouTube's 14 advertiser-unfriendly categories.

        Uses Claude Haiku with a specialised prompt that instructs the model to
        consider EDSA (Educational, Documentary, Scientific, Artistic) exception
        eligibility.

        Financial crime content typically triggers:
        - Category 9 (controversial issues): mild–moderate
        - Category 11 (dishonest behavior): none (documentary ≠ how-to)
        - Category 2 (violence): none (financial crime = non-violent)
        """
        user_message = (
            f"# Title\n{title}\n\n# Description\n{description}\n\n# Full Script\n{script}"
        )

        raw, cost = await self._call_claude(
            system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4_096,
        )

        data = self._parse_json(raw)

        # Build CategoryRating objects for each category
        categories: dict[str, CategoryRating] = {}
        raw_cats = data.get("categories", {})
        for cat_key in CATEGORIES:
            if cat_key in raw_cats:
                cat_data = raw_cats[cat_key]
                categories[cat_key] = CategoryRating(
                    category=CATEGORY_LABELS.get(cat_key, cat_key),
                    severity=cat_data.get("severity", "none"),
                    confidence=cat_data.get("confidence", 0.8),
                    reasoning=cat_data.get("reasoning", ""),
                    edsa_mitigated=cat_data.get("edsa_mitigated", False),
                )
            else:
                categories[cat_key] = CategoryRating(
                    category=CATEGORY_LABELS.get(cat_key, cat_key),
                    severity="none",
                    confidence=0.5,
                    reasoning="Not evaluated by model",
                    edsa_mitigated=False,
                )

        # Build flagged terms
        flagged_terms: list[FlaggedTerm] = []
        for ft in data.get("flagged_terms", []):
            flagged_terms.append(
                FlaggedTerm(
                    term=ft.get("term", ""),
                    location=ft.get("location", "script_body"),
                    category=ft.get("category", ""),
                    severity=ft.get("severity", "mild"),
                    safe_alternative=ft.get("safe_alternative"),
                )
            )

        # Build recommended self-cert from category severities
        recommended: dict[str, str] = {}
        for cat_key, rating in categories.items():
            recommended[cat_key] = rating.severity

        overall_risk = data.get("overall_risk", "medium")

        classification = ContentClassification(
            categories=categories,
            overall_risk=cast('Literal["low", "medium", "high"]', overall_risk),
            edsa_eligible=bool(data.get("edsa_eligible", True)),
            edsa_reasoning=str(data.get("edsa_reasoning", "")),
            recommended_self_cert=recommended,
            flagged_terms=flagged_terms,
            suggested_fixes=list(data.get("suggested_fixes", [])),
            classification_cost_usd=float(cost),
        )

        await logger.ainfo(
            "script_classified",
            overall_risk=classification.overall_risk,
            edsa_eligible=classification.edsa_eligible,
            flagged_count=len(flagged_terms),
            cost_usd=str(cost),
        )

        return classification

    async def classify_thumbnail(
        self,
        thumbnail_path: str,
    ) -> ThumbnailClassification:
        """Classify a thumbnail against YouTube's image policies.

        Uses Claude's vision capability.  YouTube scans thumbnails
        INDEPENDENTLY from video content — a graphic thumbnail triggers
        demonetisation even if the video is clean.
        """
        path = Path(thumbnail_path)
        if not path.is_file():
            raise ContentClassifierError(f"Thumbnail not found: {thumbnail_path}")

        image_data = path.read_bytes()
        b64 = base64.standard_b64encode(image_data).decode()
        mime = mimetypes.guess_type(str(path))[0] or "image/png"

        user_content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": b64,
                },
            },
            {
                "type": "text",
                "text": "Analyse this YouTube thumbnail for ad-suitability policy violations.",
            },
        ]

        raw, cost = await self._call_claude(
            system_prompt=THUMBNAIL_SYSTEM_PROMPT,
            user_message=user_content,
            max_tokens=1_024,
        )

        data = self._parse_json(raw)

        result = ThumbnailClassification(
            thumbnail_path=thumbnail_path,
            is_safe=bool(data.get("is_safe", True)),
            overall_risk=data.get("overall_risk", "low"),
            flags=list(data.get("flags", [])),
            reasoning=str(data.get("reasoning", "")),
        )

        await logger.ainfo(
            "thumbnail_classified",
            is_safe=result.is_safe,
            risk=result.overall_risk,
            flags=result.flags,
            cost_usd=str(cost),
        )

        return result

    def generate_self_cert_answers(
        self,
        classification: ContentClassification,
    ) -> SelfCertAnswers:
        """Convert a classification into YouTube's self-certification answers.

        CRITICAL: Answers are generated HONESTLY.  Short-term yellow-icon pain
        builds long-term trust score.  After ~20 honest ratings YouTube shifts
        from its own classifiers to trusting the channel's self-cert.
        Intentional misrepresentation risks YPP removal.

        For financial crime documentaries, typical answers:
        - Violence: "none" (financial crime is non-violent)
        - Language: "none" or "mild" (use coded language from bible)
        - Controversial: "mild" to "moderate" (fraud is newsworthy)
        - Dishonest behavior: "none" (documentary about crime ≠ teaching crime)
        - Everything else: "none"
        """
        cats = classification.categories

        def _sev(key: str) -> str:
            r = cats.get(key)
            return r.severity if r else "none"

        # Clamp values to what each SelfCertAnswers field accepts
        lang = _sev("inappropriate_language")

        violence = _sev("violence")

        shocking_raw = _sev("shocking")
        shocking = shocking_raw if shocking_raw in ("none", "mild") else "mild"

        controversial_raw = _sev("controversial_issues")
        controversial = (
            controversial_raw if controversial_raw in ("none", "mild", "moderate") else "moderate"
        )

        sensitive_raw = _sev("sensitive_events")
        sensitive = sensitive_raw if sensitive_raw in ("none", "mild") else "mild"

        # Average confidence across categories
        confidences = [r.confidence for r in cats.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        return SelfCertAnswers(
            inappropriate_language=lang,  # type: ignore[arg-type]
            violence=violence,  # type: ignore[arg-type]
            adult_content="none",
            shocking=shocking,  # type: ignore[arg-type]
            harmful_acts="none",
            hateful="none",
            drugs="none",
            firearms="none",
            controversial=controversial,  # type: ignore[arg-type]
            sensitive_events=sensitive,  # type: ignore[arg-type]
            dishonest_behavior="none",
            family_inappropriate="none",
            incendiary="none",
            tobacco="none",
            confidence_score=round(avg_confidence, 3),
        )

    async def check_first_30_seconds(self, script: str) -> First30sCheck:
        """Check the first ~30 seconds of narration for demonetisation triggers.

        YouTube's classifier weights the first 7-8 seconds most heavily.
        Forbidden words in the opening can trigger automatic demonetisation
        regardless of the rest of the video.
        """
        opening = _extract_first_30s(script)

        # Fast local check first — catch obvious forbidden words
        local_flagged: list[FlaggedTerm] = []
        coded_violations: list[str] = []
        words = re.findall(r"[a-zA-Z']+", opening.lower())

        for word in words:
            if word in OPENING_FORBIDDEN:
                alt = CODED_LANGUAGE.get(word)
                local_flagged.append(
                    FlaggedTerm(
                        term=word,
                        location="first_30_seconds",
                        category="inappropriate_language"
                        if word
                        in (
                            "fuck",
                            "shit",
                            "bitch",
                            "damn",
                        )
                        else "violence",
                        severity="moderate",
                        safe_alternative=alt,
                    )
                )
                if alt:
                    coded_violations.append(f'"{word}" → use "{alt}"')

        # If local check already found issues, still run LLM for nuance
        raw, _cost = await self._call_claude(
            system_prompt=FIRST_30S_SYSTEM_PROMPT,
            user_message=f"# Opening narration (~first 30 seconds)\n\n{opening}",
            max_tokens=2_048,
        )

        data = self._parse_json(raw)

        # Merge LLM flagged terms with local ones (deduplicate by term)
        seen_terms = {ft.term for ft in local_flagged}
        for ft_data in data.get("flagged_terms", []):
            term = ft_data.get("term", "")
            if term.lower() not in seen_terms:
                local_flagged.append(
                    FlaggedTerm(
                        term=term,
                        location="first_30_seconds",
                        category=ft_data.get("category", "violence"),
                        severity=ft_data.get("severity", "mild"),
                        safe_alternative=ft_data.get("safe_alternative"),
                    )
                )
                seen_terms.add(term.lower())

        llm_violations: list[str] = data.get("coded_language_violations", [])
        for v in llm_violations:
            if v not in coded_violations:
                coded_violations.append(v)

        recommendations: list[str] = data.get("recommendations", [])
        passed = bool(data.get("passed", True)) and not local_flagged

        return First30sCheck(
            passed=passed,
            flagged_terms=local_flagged,
            coded_language_violations=coded_violations,
            recommendations=recommendations,
        )

    async def check_title_safety(self, title: str) -> TitleSafetyCheck:
        """Check a title against known demonetisation trigger patterns.

        From the Nerd City study: ~3,000+ words trigger demonetisation in
        titles.  Hoopoz maintains 16,574 flagged keywords.  We check against
        a curated subset of the most impactful terms.

        Any profanity in the title = near-certain zero revenue.
        """
        title_lower = title.lower()
        words = re.findall(r"[a-zA-Z']+", title_lower)

        flagged: list[str] = [w for w in words if w in TITLE_TRIGGER_WORDS]

        # Determine monetisation estimate
        has_profanity = any(
            w in {"fuck", "fucking", "fucked", "fucker", "shit", "bullshit", "bitch"}
            for w in flagged
        )

        if has_profanity or len(flagged) >= 3:
            estimated = "red"
        elif len(flagged) >= 1:
            estimated = "yellow"
        else:
            estimated = "green"

        # Generate a safe alternative title
        safe_variant: str | None = None
        if flagged:
            safe_title = title
            for word in flagged:
                alt = TITLE_SAFE_ALTERNATIVES.get(word)
                if alt:
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    safe_title = pattern.sub(alt, safe_title, count=1)
            if safe_title != title:
                safe_variant = safe_title

        result = TitleSafetyCheck(
            title=title,
            is_safe=not flagged,
            flagged_words=flagged,
            safe_title_variant=safe_variant,
            estimated_monetization=estimated,  # type: ignore[arg-type]
        )

        await logger.ainfo(
            "title_safety_checked",
            title=title,
            is_safe=result.is_safe,
            flagged_count=len(flagged),
            estimated_monetization=estimated,
        )

        return result
