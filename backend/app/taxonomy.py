"""Controlled vocabularies used by profiles, search and the matching engine.

Values are stored in the database as lowercase snake_case slugs; the helpers
here normalise free text into that form and provide human readable labels.
"""

from __future__ import annotations

import re

# --- education levels, ordered from youngest to oldest learners ----------------
EDUCATION_LEVELS: list[str] = [
    "elementary",
    "middle_school",
    "high_school",
    "university",
    "graduate",
    "adult_education",
]

# --- learner proficiency a teacher works with ---------------------------------
TEACHING_LEVELS: list[str] = ["beginner", "intermediate", "advanced"]

# --- pedagogical methods ------------------------------------------------------
TEACHING_METHODS: list[str] = [
    "project_based",
    "lecture_based",
    "collaborative",
    "socratic",
    "hands_on",
    "flipped_classroom",
    "inquiry_based",
    "game_based",
    "discussion_based",
    "problem_based",
]

SUBJECTS: list[str] = [
    "mathematics",
    "physics",
    "chemistry",
    "biology",
    "computer_science",
    "english",
    "history",
    "economics",
    "business",
    "art",
    "music",
    "engineering",
    "psychology",
    "statistics",
    "artificial_intelligence",
    "machine_learning",
]

RESOURCE_TYPES: list[str] = [
    "lesson_plan",
    "worksheet",
    "slide_deck",
    "assessment",
    "project_brief",
    "reading",
    "video_guide",
    "rubric",
    "syllabus",
    "homework",
]

DIFFICULTIES: list[str] = ["beginner", "intermediate", "advanced"]

INSTITUTION_TYPES: list[str] = [
    "public_school",
    "private_school",
    "charter_school",
    "university",
    "community_college",
    "online_academy",
    "nonprofit",
    "independent",
]

# --- education-level compatibility -------------------------------------------
# How well a teacher of level A collaborates with a teacher of level B.
# Symmetric; diagonal is 1.0. Configurable via EDUCATION_COMPATIBILITY_JSON.
EDUCATION_COMPATIBILITY: dict[str, dict[str, float]] = {
    "elementary": {
        "elementary": 1.0,
        "middle_school": 0.6,
        "high_school": 0.2,
        "university": 0.1,
        "graduate": 0.1,
        "adult_education": 0.2,
    },
    "middle_school": {
        "elementary": 0.6,
        "middle_school": 1.0,
        "high_school": 0.6,
        "university": 0.2,
        "graduate": 0.1,
        "adult_education": 0.2,
    },
    "high_school": {
        "elementary": 0.2,
        "middle_school": 0.6,
        "high_school": 1.0,
        "university": 0.3,
        "graduate": 0.2,
        "adult_education": 0.4,
    },
    "university": {
        "elementary": 0.1,
        "middle_school": 0.2,
        "high_school": 0.3,
        "university": 1.0,
        "graduate": 0.7,
        "adult_education": 0.5,
    },
    "graduate": {
        "elementary": 0.1,
        "middle_school": 0.1,
        "high_school": 0.2,
        "university": 0.7,
        "graduate": 1.0,
        "adult_education": 0.4,
    },
    "adult_education": {
        "elementary": 0.2,
        "middle_school": 0.2,
        "high_school": 0.4,
        "university": 0.5,
        "graduate": 0.4,
        "adult_education": 1.0,
    },
}

# --- expertise relatedness ----------------------------------------------------
# Terms that are not identical but clearly adjacent. Used for a "soft" Jaccard
# so that {python, machine_learning, computer_science} scores highly against
# {python, artificial_intelligence, computer_science}.
RELATED_TERMS: list[tuple[str, str, float]] = [
    ("machine_learning", "artificial_intelligence", 0.9),
    ("machine_learning", "data_science", 0.8),
    ("machine_learning", "statistics", 0.7),
    ("artificial_intelligence", "computer_science", 0.7),
    ("machine_learning", "computer_science", 0.7),
    ("python", "computer_science", 0.7),
    ("python", "software_engineering", 0.7),
    ("python", "programming", 0.9),
    ("software_engineering", "computer_science", 0.8),
    ("data_science", "statistics", 0.8),
    ("statistics", "mathematics", 0.7),
    ("physics", "mathematics", 0.6),
    ("engineering", "physics", 0.6),
    ("engineering", "mathematics", 0.5),
    ("chemistry", "biology", 0.5),
    ("biology", "psychology", 0.4),
    ("economics", "business", 0.7),
    ("economics", "statistics", 0.5),
    ("business", "entrepreneurship", 0.8),
    ("english", "literature", 0.9),
    ("english", "creative_writing", 0.7),
    ("english", "writing", 0.85),
    ("literature", "creative_writing", 0.75),
    ("history", "social_studies", 0.8),
    ("history", "world_history", 0.9),
    ("history", "us_history", 0.9),
    ("us_history", "social_studies", 0.75),
    ("world_history", "social_studies", 0.75),
    ("geography", "social_studies", 0.8),
    ("civics", "social_studies", 0.85),
    ("government", "civics", 0.9),
    ("art", "design", 0.7),
    ("art", "visual_arts", 0.95),
    ("music", "art", 0.4),
    ("music", "performing_arts", 0.85),
    ("drama", "performing_arts", 0.9),
    ("theatre", "drama", 0.95),
    ("robotics", "engineering", 0.8),
    ("robotics", "computer_science", 0.6),
    ("web_development", "software_engineering", 0.8),
    ("web_development", "computer_science", 0.6),
    ("esl", "english", 0.7),
    ("esl", "linguistics", 0.75),
    ("linguistics", "english", 0.65),
    ("special_education", "psychology", 0.55),
    ("special_education", "education", 0.7),
    ("early_childhood", "elementary", 0.75),
    ("reading", "english", 0.8),
    ("reading", "literacy", 0.95),
    ("literacy", "english", 0.8),
    ("earth_science", "geology", 0.85),
    ("earth_science", "geography", 0.6),
    ("environmental_science", "biology", 0.7),
    ("environmental_science", "earth_science", 0.75),
    ("astronomy", "physics", 0.7),
    ("foreign_language", "spanish", 0.7),
    ("foreign_language", "french", 0.7),
    ("spanish", "linguistics", 0.5),
    ("french", "linguistics", 0.5),
    ("physical_education", "health", 0.7),
    ("health", "biology", 0.5),
    # Course-level subjects used by class profiles / technique seed data.
    ("calculus", "mathematics", 0.95),
    ("precalculus", "calculus", 0.9),
    ("precalculus", "mathematics", 0.9),
    ("algebra", "mathematics", 0.9),
    ("geometry", "mathematics", 0.85),
    ("linear_algebra", "mathematics", 0.9),
    ("linear_algebra", "calculus", 0.7),
    ("calculus", "statistics", 0.55),
    ("intro_cs", "computer_science", 0.95),
    ("intro_biology", "biology", 0.95),
    ("organic_chemistry", "chemistry", 0.95),
    ("general_chemistry", "chemistry", 0.95),
]

# Exact synonyms collapse to a single canonical slug before any comparison.
SYNONYMS: dict[str, str] = {
    "ai": "artificial_intelligence",
    "a_i": "artificial_intelligence",
    "ml": "machine_learning",
    "cs": "computer_science",
    "comp_sci": "computer_science",
    "compsci": "computer_science",
    "maths": "mathematics",
    "math": "mathematics",
    "stats": "statistics",
    "phys_ed": "physical_education",
    "lit": "literature",
    "ela": "english",
    "econ": "economics",
    "bio": "biology",
    "chem": "chemistry",
    "swe": "software_engineering",
    "programming_languages": "programming",
    "deep_learning": "machine_learning",
    "data_analytics": "data_science",
    "calc": "calculus",
    "differential_calculus": "calculus",
    "integral_calculus": "calculus",
    "intro_to_cs": "intro_cs",
    "introductory_cs": "intro_cs",
    "intro_to_biology": "intro_biology",
    "introductory_biology": "intro_biology",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """'Machine Learning' -> 'machine_learning'."""
    return _SLUG_RE.sub("_", value.strip().lower()).strip("_")


def canonical_term(value: str) -> str:
    """Normalise a subject/expertise term to its canonical slug."""
    slug = slugify(value)
    return SYNONYMS.get(slug, slug)


def canonical_terms(values: list[str] | None) -> set[str]:
    return {canonical_term(v) for v in (values or []) if v and v.strip()}


def humanize(value: str) -> str:
    """'high_school' -> 'High School'."""
    special = {"artificial_intelligence": "Artificial Intelligence", "ai": "AI"}
    if value in special:
        return special[value]
    return " ".join(word.capitalize() for word in value.split("_"))


_RELATEDNESS: dict[tuple[str, str], float] = {}
for _a, _b, _score in RELATED_TERMS:
    _RELATEDNESS[(_a, _b)] = _score
    _RELATEDNESS[(_b, _a)] = _score


def term_relatedness(a: str, b: str) -> float:
    """Similarity in [0, 1] between two expertise terms."""
    if a == b:
        return 1.0
    return _RELATEDNESS.get((a, b), 0.0)


# Minimum relatedness for "same or closely related field" hard filters.
CLOSE_FIELD_THRESHOLD = 0.6


def fields_compatible(
    a: str | None,
    b: str | None,
    *,
    min_score: float = CLOSE_FIELD_THRESHOLD,
) -> bool:
    """True when two subject labels are the same field or closely adjacent."""
    if not a or not b:
        return False
    ca, cb = canonical_term(a), canonical_term(b)
    if ca == cb:
        return True
    if term_relatedness(ca, cb) >= min_score:
        return True
    # Free-text containment for labels like "ap_calculus" vs "calculus".
    shorter, longer = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return len(shorter) >= 4 and (
        longer == shorter
        or longer.startswith(f"{shorter}_")
        or longer.endswith(f"_{shorter}")
        or f"_{shorter}_" in longer
    )


def education_compatibility(a: str, b: str, overrides: dict[str, dict[str, float]] | None = None) -> float:
    """Compatibility in [0, 1] between two education levels."""
    if overrides:
        value = overrides.get(a, {}).get(b)
        if value is not None:
            return float(value)
    if a == b:
        return 1.0
    return EDUCATION_COMPATIBILITY.get(a, {}).get(b, 0.1)
