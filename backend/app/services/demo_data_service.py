"""Synthetic data generation for demos, load testing and judging.

The data is *internally consistent*: an elementary teacher is never given
"Advanced Quantum Computing", class sizes follow the education level, and the
prose bio matches the structured attributes (which is what makes the semantic
embeddings meaningful rather than noise).
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from itertools import accumulate

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import Connection, ConnectionStatus
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.recommendation import RecommendationEvent
from app.models.resource import Resource
from app.models.user import User
from app.services.demo_data_catalog import (
    BIO_HOOKS,
    CITIES,
    CITY_WEIGHTS,
    INSTITUTION_LOOKUP,
    LEVEL_PROFILES,
    MESSAGE_OPENERS,
    MESSAGE_REPLIES,
    METHOD_PHRASES,
    RATING_COMMENTS,
    RESOURCE_KINDS,
    RESOURCE_TITLE_TEMPLATES,
    STYLE_TAILS,
    SUBJECT_EXPERTISE,
    TOPICS,
)
from app.services.embedding_service import EmbeddingService, HashingEmbeddingProvider
from app.utils.auth import hash_password

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "DemoPassword123!"

# Building an HNSW index row by row during a bulk load is the single most
# expensive part of seeding. We drop the vector indexes first and rebuild them
# once at the end, which is an order of magnitude faster.
VECTOR_INDEXES: dict[str, str] = {
    "ix_teacher_profiles_embedding_hnsw": (
        "CREATE INDEX ix_teacher_profiles_embedding_hnsw ON teacher_profiles "
        "USING hnsw (teaching_style_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    ),
    "ix_resources_embedding_hnsw": (
        "CREATE INDEX ix_resources_embedding_hnsw ON resources "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    ),
}


@dataclass
class GenerationCounts:
    users: int = 10_000
    resources: int = 50_000
    ratings: int = 30_000
    connections: int = 20_000
    conversations: int = 500


@dataclass
class GenerationStats:
    users: int = 0
    profiles: int = 0
    resources: int = 0
    ratings: int = 0
    connections: int = 0
    conversations: int = 0
    messages: int = 0
    seconds: float = 0.0
    demo_accounts: list[str] = field(default_factory=list)


class DemoDataGenerator:
    """Builds a realistic EduMatch dataset in bulk."""

    def __init__(
        self,
        db: AsyncSession,
        counts: GenerationCounts | None = None,
        *,
        seed: int = 2026,
        batch_size: int = 1000,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.counts = counts or GenerationCounts()
        self.random = random.Random(seed)
        self.batch_size = batch_size
        # Always use the deterministic provider for bulk generation: 60k+ API
        # calls would be slow and expensive, and reproducibility matters here.
        self.embeddings = embeddings or EmbeddingService(
            HashingEmbeddingProvider(EmbeddingService().dim)
        )
        self._hasher_cache: dict[str, str] = {}
        # Soft indexes used to bias connections / ratings toward similar peers.
        self._users_by_city: dict[str, list[uuid.UUID]] = {}
        self._users_by_subject: dict[str, list[uuid.UUID]] = {}
        self._profile_meta: dict[uuid.UUID, dict] = {}

    # --- helpers ---------------------------------------------------------- #
    def _password_hash(self, password: str = DEMO_PASSWORD) -> str:
        """Hash once and reuse: Argon2 is deliberately slow, and this is fake data."""
        if password not in self._hasher_cache:
            self._hasher_cache[password] = hash_password(password)
        return self._hasher_cache[password]

    def _pick_city_index(self) -> int:
        return self.random.choices(range(len(CITIES)), weights=CITY_WEIGHTS, k=1)[0]

    def _institution_bucket(self, level: str, institution_type: str) -> str:
        """Map education level + institution_type to a catalog bucket."""
        if institution_type == "community_college":
            return "community_college"
        if institution_type in ("online_academy", "nonprofit", "independent"):
            return "adult"
        if institution_type == "university" or level in ("university", "graduate"):
            return "university"
        if level == "adult_education":
            return "adult"
        if level == "elementary":
            return "elementary"
        if level == "middle_school":
            return "middle_school"
        return "high_school"

    def _institution_name(self, level: str, city: str, institution_type: str) -> str:
        bucket = self._institution_bucket(level, institution_type)
        catalog = INSTITUTION_LOOKUP.get(city, {})
        # Prefer the exact bucket; allow narrow, compatible fallbacks only.
        fallbacks = {
            "elementary": ("elementary", "middle_school"),
            "middle_school": ("middle_school", "elementary"),
            "high_school": ("high_school",),
            "university": ("university",),
            "community_college": ("community_college", "adult"),
            "adult": ("adult", "community_college"),
        }
        names: list[str] = []
        for key in fallbacks.get(bucket, (bucket,)):
            names = catalog.get(key) or []
            if names:
                break
        if names:
            return self.random.choice(names)

        town = city.split(",")[0]
        if bucket == "university":
            return self.random.choice(
                [
                    f"University of {town}",
                    f"{town} Institute of Technology",
                    f"{town} State University",
                ]
            )
        if bucket == "community_college":
            return self.random.choice(
                [f"{town} Community College", f"{town} Technical College"]
            )
        if bucket == "adult":
            return self.random.choice(
                [
                    f"{town} Adult Learning Centre",
                    f"{town} Continuing Education",
                    f"{town} Skills Hub",
                ]
            )
        if bucket == "elementary":
            return self.random.choice(
                [f"{town} Elementary School", f"{town} Primary School"]
            )
        if bucket == "middle_school":
            return self.random.choice(
                [f"{town} Middle School", f"{town} Junior High School"]
            )
        return self.random.choice(
            [
                f"{town} High School",
                f"{town} Academy",
                f"{town} Preparatory School",
                f"International School of {town}",
            ]
        )

    def _sample_methods(self, level: str, k: int | None = None) -> list[str]:
        weights = LEVEL_PROFILES[level]["method_weights"]
        methods = [m for m, w in weights.items() if w > 0]
        method_weights = [weights[m] for m in methods]
        count = k if k is not None else self.random.randint(1, min(3, len(methods)))
        chosen: list[str] = []
        pool = list(methods)
        pool_weights = list(method_weights)
        for _ in range(count):
            pick = self.random.choices(pool, weights=pool_weights, k=1)[0]
            chosen.append(pick)
            idx = pool.index(pick)
            pool.pop(idx)
            pool_weights.pop(idx)
            if not pool:
                break
        return chosen

    def _sample_expertise(self, subjects: list[str], level: str, k: int | None = None) -> list[str]:
        pool: list[str] = []
        for subject in subjects:
            pool.extend(SUBJECT_EXPERTISE.get(subject, []))
        pool.extend(LEVEL_PROFILES[level]["expertise"])
        # Preserve order while uniquifying so sampling stays stable.
        seen: set[str] = set()
        unique = []
        for term in pool:
            if term not in seen:
                seen.add(term)
                unique.append(term)
        count = k if k is not None else self.random.randint(1, min(3, len(unique)))
        return self.random.sample(unique, k=min(count, len(unique)))

    def _education_levels_for(self, primary: str) -> list[str]:
        """Most teachers stick to one band; ~18% span an adjacent level.

        University never pairs with graduate here: their class-size ranges do
        not overlap, and mixed profiles would violate the consistency contract
        unless class size is derived from the intersection (see _class_size_for).
        Graduate may still list university as an adjacent band.
        """
        levels = [primary]
        if self.random.random() > 0.18:
            return levels
        adjacency = {
            "elementary": ["middle_school"],
            "middle_school": ["elementary", "high_school"],
            "high_school": ["middle_school", "adult_education"],
            "university": ["adult_education"],
            "graduate": ["university"],
            "adult_education": ["high_school", "university"],
        }
        extras = adjacency.get(primary, [])
        if extras:
            levels.append(self.random.choice(extras))
        return levels

    def _class_size_for(self, levels: list[str]) -> int:
        """Sample a class size compatible with every education level taught."""
        low = max(LEVEL_PROFILES[level]["class_size"][0] for level in levels)
        high = min(LEVEL_PROFILES[level]["class_size"][1] for level in levels)
        if low > high:
            # No overlap — use the most restrictive band's full range so we
            # never exceed any listed level's maximum.
            restrictive = min(levels, key=lambda level: LEVEL_PROFILES[level]["class_size"][1])
            low, high = LEVEL_PROFILES[restrictive]["class_size"]
        return self.random.randint(low, high)

    def _years_experience(self, level: str) -> int:
        # Career arcs differ by sector; graduate faculty skew more senior.
        bands = {
            "elementary": (1, 28),
            "middle_school": (1, 30),
            "high_school": (1, 32),
            "university": (2, 35),
            "graduate": (4, 40),
            "adult_education": (1, 25),
        }
        low, high = bands[level]
        # Mild right skew: more early/mid-career than late-career.
        years = int(self.random.betavariate(2.0, 3.2) * (high - low) + low)
        return max(low, min(high, years))

    def _teaching_style_text(self, methods: list[str], subjects: list[str], level: str) -> str:
        phrases = [METHOD_PHRASES[m] for m in methods]
        subject_text = subjects[0].replace("_", " ")
        level_text = level.replace("_", " ")
        leads = [
            f"In {subject_text} I rely on {phrases[0]}",
            f"My {subject_text} classroom is built around {phrases[0]}",
            f"When I teach {subject_text}, I centre {phrases[0]}",
            f"At the {level_text} level I organise {subject_text} around {phrases[0]}",
            f"Students encounter {subject_text} through {phrases[0]}",
        ]
        lead = self.random.choice(leads)
        if len(phrases) > 1:
            connector = self.random.choice(
                [", supported by ", ", then deepen with ", ", paired with "]
            )
            lead += f"{connector}{phrases[1]}"
        if len(phrases) > 2:
            lead += f", and occasionally {phrases[2]}"
        return f"{lead}. {self.random.choice(STYLE_TAILS)}"

    def _bio_text(
        self,
        years: int,
        levels: list[str],
        subjects: list[str],
        expertise: list[str],
        institution: str,
        methods: list[str],
    ) -> str:
        subject_text = " and ".join(s.replace("_", " ") for s in subjects[:2])
        level_text = levels[0].replace("_", " ")
        method_text = methods[0].replace("_", " ")
        expertise_text = expertise[0].replace("_", " ") if expertise else "curriculum design"
        seniority = (
            "early-career"
            if years < 5
            else "mid-career"
            if years < 15
            else "veteran"
        )
        openings = [
            f"{years}-year {seniority} {level_text} {subject_text} teacher at {institution}.",
            f"I have spent {years} years building {subject_text} curricula for "
            f"{level_text} learners at {institution}.",
            f"{level_text.capitalize()} {subject_text} educator ({years} yrs) focused on "
            f"{expertise_text}, currently at {institution}.",
            f"At {institution} I teach {subject_text} with a {method_text} approach "
            f"after {years} years in classrooms.",
            f"{seniority.capitalize()} educator: {subject_text} at {level_text} level, "
            f"based at {institution} for most of my {years}-year career.",
        ]
        if len(levels) > 1:
            openings.append(
                f"I bridge {levels[0].replace('_', ' ')} and "
                f"{levels[1].replace('_', ' ')} {subject_text} at {institution} "
                f"({years} years teaching)."
            )
        middle = [
            f"Specialty: {expertise_text}.",
            f"Known for {method_text} units that travel well between schools.",
            f"Currently iterating on {expertise_text} with my department.",
            f"Most of my energy goes into {method_text} experiences students remember.",
        ]
        return (
            f"{self.random.choice(openings)} {self.random.choice(middle)} "
            f"{self.random.choice(BIO_HOOKS)}"
        )

    def _make_profile_payload(self, level: str, city_index: int | None = None) -> dict:
        spec = LEVEL_PROFILES[level]
        idx = self._pick_city_index() if city_index is None else city_index
        city, lat, lon, languages = CITIES[idx]

        subject_count = self.random.choices([1, 2, 3], weights=[35, 45, 20], k=1)[0]
        subjects = self.random.sample(spec["subjects"], k=min(subject_count, len(spec["subjects"])))
        # ~35% of CS-adjacent high-school / uni teachers also list python explicitly.
        if (
            "computer_science" in subjects
            and level in ("high_school", "university", "adult_education")
            and self.random.random() < 0.35
            and "python" not in subjects
        ):
            subjects = subjects + ["python"]

        expertise = self._sample_expertise(subjects, level)
        methods = self._sample_methods(level)
        education_levels = self._education_levels_for(level)
        teaching_levels = self.random.sample(
            spec["levels"], k=self.random.randint(1, len(spec["levels"]))
        )
        institution_type = self.random.choice(spec["institution_types"])
        institution = self._institution_name(level, city, institution_type)
        years = self._years_experience(level)

        # Speak all local languages with decaying probability.
        lang_count = 1
        for i in range(1, len(languages)):
            if self.random.random() < 0.55 / i:
                lang_count = i + 1
        spoken = languages[:lang_count]

        # Tighter jitter in dense cities so proximity scoring still clusters.
        jitter = 0.08 if CITY_WEIGHTS[idx] >= 5 else 0.14

        return {
            "education_levels": education_levels,
            "subjects": subjects,
            "fields_of_expertise": expertise,
            "teaching_methods": methods,
            "teaching_levels": teaching_levels,
            "teaching_style": self._teaching_style_text(methods, subjects, level),
            "bio": self._bio_text(years, education_levels, subjects, expertise, institution, methods),
            "class_size": self._class_size_for(education_levels),
            "years_experience": years,
            "languages": spoken,
            "institution": institution,
            "institution_type": institution_type,
            "location_name": city,
            "latitude": round(lat + self.random.uniform(-jitter, jitter), 2),
            "longitude": round(lon + self.random.uniform(-jitter, jitter), 2),
        }

    def _index_profile(self, user_id: uuid.UUID, profile: dict) -> None:
        city = profile["location_name"]
        self._users_by_city.setdefault(city, []).append(user_id)
        for subject in profile["subjects"]:
            self._users_by_subject.setdefault(subject, []).append(user_id)
        self._profile_meta[user_id] = {
            "city": city,
            "subjects": list(profile["subjects"]),
            "levels": list(profile["education_levels"]),
        }

    def _biased_peer(self, user_id: uuid.UUID, pool: list[uuid.UUID]) -> uuid.UUID:
        """Prefer same-city or same-subject peers (~70%), else uniform."""
        meta = self._profile_meta.get(user_id)
        if meta and self.random.random() < 0.70:
            candidates: list[uuid.UUID] = []
            city_peers = self._users_by_city.get(meta["city"], [])
            subject_peers: list[uuid.UUID] = []
            for subject in meta["subjects"]:
                subject_peers.extend(self._users_by_subject.get(subject, []))
            candidates.extend(city_peers)
            candidates.extend(subject_peers)
            candidates = [c for c in candidates if c != user_id]
            if candidates:
                return candidates[self.random.randrange(len(candidates))]
        peer = pool[self.random.randrange(len(pool))]
        while peer == user_id and len(pool) > 1:
            peer = pool[self.random.randrange(len(pool))]
        return peer

    async def _bulk_insert(self, table, rows: list[dict]) -> int:
        for start in range(0, len(rows), self.batch_size):
            chunk = rows[start : start + self.batch_size]
            await self.db.execute(insert(table), chunk)
            await self.db.commit()
        return len(rows)

    async def drop_vector_indexes(self) -> None:
        for name in VECTOR_INDEXES:
            await self.db.execute(text(f"DROP INDEX IF EXISTS {name}"))
        await self.db.commit()
        logger.info("Dropped vector indexes for the bulk load")

    async def create_vector_indexes(self) -> None:
        started = time.perf_counter()
        await self.db.execute(text("SET maintenance_work_mem = '256MB'"))
        for name, statement in VECTOR_INDEXES.items():
            await self.db.execute(text(f"DROP INDEX IF EXISTS {name}"))
            await self.db.execute(text(statement))
        await self.db.execute(text("ANALYZE teacher_profiles"))
        await self.db.execute(text("ANALYZE resources"))
        await self.db.commit()
        logger.info("Rebuilt vector indexes in %.1fs", time.perf_counter() - started)

    # --- steps ------------------------------------------------------------- #
    async def truncate(self) -> None:
        """Wipe generated data (keeps the schema)."""
        for model in (
            RecommendationEvent,
            Message,
            ConversationParticipant,
            Conversation,
            Rating,
            Connection,
            Resource,
            TeacherProfile,
            User,
        ):
            await self.db.execute(delete(model))
        await self.db.commit()
        self._users_by_city.clear()
        self._users_by_subject.clear()
        self._profile_meta.clear()
        logger.info("Existing data cleared")

    async def create_demo_accounts(self) -> list[tuple[uuid.UUID, dict]]:
        """The handful of accounts a judge will actually log into.

        Alice and Bob are deliberately near-identical (high school, computer
        science, Python, project-based, 8 km apart); Carol teaches the same
        subject at a different level, in a different city, in a different style.
        Alice's top match must therefore be Bob, not Carol.
        """
        password_hash = self._password_hash()
        specs: list[tuple[str, str, str, dict]] = [
            (
                "demo_teacher@example.com",
                "Alice",
                "Nguyen",
                {
                    "education_levels": ["high_school"],
                    "subjects": ["computer_science", "python"],
                    "fields_of_expertise": ["software_engineering", "robotics"],
                    "teaching_methods": ["project_based", "collaborative"],
                    "teaching_levels": ["beginner", "intermediate"],
                    "teaching_style": (
                        "Project-based and collaborative: my computer science students build real "
                        "software end to end in small teams that critique each other's work. "
                        "Every unit ends with something students can show to a real audience."
                    ),
                    "bio": (
                        "5-year mid-career high school computer science and python teacher at "
                        "Boston Latin School. Specialty: software engineering. I run an after-school "
                        "robotics club that draws students who rarely speak up in class."
                    ),
                    "class_size": 25,
                    "years_experience": 5,
                    "languages": ["English"],
                    "institution": "Boston Latin School",
                    "institution_type": "public_school",
                    "location_name": "Boston, Massachusetts",
                    "latitude": 42.36,
                    "longitude": -71.06,
                },
            ),
            (
                "demo_bob@example.com",
                "Bob",
                "Martinez",
                {
                    "education_levels": ["high_school"],
                    "subjects": ["computer_science", "python"],
                    "fields_of_expertise": ["software_engineering", "web_development"],
                    "teaching_methods": ["project_based", "collaborative"],
                    "teaching_levels": ["beginner", "intermediate"],
                    "teaching_style": (
                        "Project-based and collaborative. Students work in pairs to ship a working "
                        "app each unit, with peer code review built into the process. We iterate "
                        "publicly: drafts on the wall, critique protocols, revise again."
                    ),
                    "bio": (
                        "At Cambridge Rindge and Latin School I teach computer science and python with a "
                        "project-based approach after 6 years in classrooms. Known for project-based "
                        "units that travel well between schools. I publish open resources because "
                        "locked PDFs help nobody."
                    ),
                    "class_size": 28,
                    "years_experience": 6,
                    "languages": ["English", "Spanish"],
                    "institution": "Cambridge Rindge and Latin School",
                    "institution_type": "public_school",
                    "location_name": "Cambridge, Massachusetts",
                    "latitude": 42.37,
                    "longitude": -71.11,
                },
            ),
            (
                "demo_carol@example.com",
                "Carol",
                "Whitfield",
                {
                    "education_levels": ["university"],
                    "subjects": ["computer_science", "machine_learning"],
                    "fields_of_expertise": ["machine_learning", "research_methods"],
                    "teaching_methods": ["lecture_based", "socratic"],
                    "teaching_levels": ["advanced"],
                    "teaching_style": (
                        "Lecture-based with Socratic seminars. I cover the mathematics of machine "
                        "learning carefully before any implementation work, then push students to "
                        "justify every modelling choice. I publish exemplars early so students know "
                        "what 'good' looks like."
                    ),
                    "bio": (
                        "12-year veteran university computer science and machine learning educator at "
                        "Columbia University. Currently iterating on research methods with my "
                        "department. Colleagues borrow my unit maps more than my slide decks."
                    ),
                    "class_size": 90,
                    "years_experience": 12,
                    "languages": ["English"],
                    "institution": "Columbia University",
                    "institution_type": "university",
                    "location_name": "New York, New York",
                    "latitude": 40.71,
                    "longitude": -74.01,
                },
            ),
            (
                "demo_dana@example.com",
                "Dana",
                "Okafor",
                {
                    "education_levels": ["high_school"],
                    "subjects": ["physics", "engineering"],
                    "fields_of_expertise": ["robotics", "lab_design"],
                    "teaching_methods": ["hands_on", "project_based"],
                    "teaching_levels": ["intermediate", "advanced"],
                    "teaching_style": (
                        "Hands-on and project-based: every physics concept arrives through a build, "
                        "a measurement and an argument about the data. I keep a living question "
                        "board; unfinished curiosity becomes next week's hook."
                    ),
                    "bio": (
                        "8-year mid-career high school physics and engineering teacher at Somerville "
                        "High School. Specialty: robotics. Outside class I coach the robotics team "
                        "and occasionally journalism, depending on the year."
                    ),
                    "class_size": 24,
                    "years_experience": 8,
                    "languages": ["English"],
                    "institution": "Somerville High School",
                    "institution_type": "public_school",
                    "location_name": "Somerville, Massachusetts",
                    "latitude": 42.39,
                    "longitude": -71.10,
                },
            ),
        ]

        created: list[tuple[uuid.UUID, dict]] = []
        user_rows, profile_rows = [], []
        for email, first, last, profile in specs:
            user_id = uuid.uuid4()
            user_rows.append(
                {
                    "id": user_id,
                    "email": email,
                    "password_hash": password_hash,
                    "first_name": first,
                    "last_name": last,
                    "is_verified": True,
                    "is_active": True,
                }
            )
            profile_rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    **profile,
                    "teaching_style_embedding": await self._embed_profile(profile),
                    "average_rating": 0.0,
                    "rating_count": 0,
                }
            )
            self._index_profile(user_id, profile)
            created.append((user_id, {"email": email, "first_name": first, **profile}))

        await self._bulk_insert(User, user_rows)
        await self._bulk_insert(TeacherProfile, profile_rows)
        logger.info("Created %d demo accounts", len(created))
        return created

    async def _embed_profile(self, profile: dict) -> list[float]:
        text_value = EmbeddingService.build_profile_text(
            teaching_style=profile.get("teaching_style"),
            bio=profile.get("bio"),
            fields_of_expertise=profile.get("fields_of_expertise"),
            subjects=profile.get("subjects"),
            teaching_methods=profile.get("teaching_methods"),
            education_levels=profile.get("education_levels"),
        )
        return await self.embeddings.generate_embedding(text_value)

    async def generate_users(self, count: int) -> list[uuid.UUID]:
        from faker import Faker

        faker = Faker()
        Faker.seed(self.random.randint(0, 10**6))
        # Locale variety for names without changing email pattern.
        faker_locales = [
            Faker("en_US"),
            Faker("en_GB"),
            Faker("es_ES"),
            Faker("fr_FR"),
            Faker("de_DE"),
            Faker("pt_BR"),
            Faker("hi_IN"),
            Faker("ja_JP"),
        ]
        for locale_faker in faker_locales:
            locale_faker.seed_instance(self.random.randint(0, 10**6))

        password_hash = self._password_hash()
        levels = list(LEVEL_PROFILES)
        weights = [0.14, 0.16, 0.32, 0.20, 0.08, 0.10]  # high school heavy

        user_ids: list[uuid.UUID] = []
        user_rows: list[dict] = []
        profile_rows: list[dict] = []
        texts: list[str] = []
        pending_profiles: list[dict] = []

        for index in range(count):
            user_id = uuid.uuid4()
            user_ids.append(user_id)
            name_faker = self.random.choice(faker_locales + [faker])
            first, last = name_faker.first_name(), name_faker.last_name()
            # Keep ASCII-ish emails stable even when display names have accents.
            user_rows.append(
                {
                    "id": user_id,
                    "email": f"teacher{index}@edumatch.demo",
                    "password_hash": password_hash,
                    "first_name": first[:80],
                    "last_name": last[:80],
                    "is_verified": self.random.random() < 0.42,
                    "is_active": True,
                }
            )
            level = self.random.choices(levels, weights=weights, k=1)[0]
            profile = self._make_profile_payload(level)
            self._index_profile(user_id, profile)
            pending_profiles.append({"id": uuid.uuid4(), "user_id": user_id, **profile})
            texts.append(
                EmbeddingService.build_profile_text(
                    teaching_style=profile["teaching_style"],
                    bio=profile["bio"],
                    fields_of_expertise=profile["fields_of_expertise"],
                    subjects=profile["subjects"],
                    teaching_methods=profile["teaching_methods"],
                    education_levels=profile["education_levels"],
                )
            )

        vectors = await self.embeddings.generate_embeddings(texts)
        for profile_row, vector in zip(pending_profiles, vectors):
            profile_row["teaching_style_embedding"] = vector
            profile_row["average_rating"] = 0.0
            profile_row["rating_count"] = 0
            profile_rows.append(profile_row)

        await self._bulk_insert(User, user_rows)
        await self._bulk_insert(TeacherProfile, profile_rows)
        logger.info("Inserted %d users with profiles", count)
        return user_ids

    async def generate_resources(self, owner_ids: list[uuid.UUID], count: int) -> int:
        """Resources consistent with their owner's subjects and level.

        Ownership follows a mild power law so a minority of educators look like
        prolific publishers (closer to real repositories). Owners are ordered by
        user_id so the Zipf weights are deterministic under a fixed seed.
        """
        owners = (
            await self.db.execute(
                select(
                    TeacherProfile.user_id,
                    TeacherProfile.subjects,
                    TeacherProfile.education_levels,
                    TeacherProfile.teaching_methods,
                ).order_by(TeacherProfile.user_id)
            )
        ).all()
        if not owners:
            return 0

        # Zipf-ish weights over the stable owner order; cum_weights avoids
        # rebuilding the cumulative array on every one of N resource draws.
        owner_weights = [1.0 / ((i + 1) ** 0.55) for i in range(len(owners))]
        owner_cum_weights = list(accumulate(owner_weights))
        materials_by_type = {
            "lesson_plan": ["projector", "whiteboard"],
            "worksheet": ["printer", "pencils"],
            "slide_deck": ["projector", "computer"],
            "project_brief": ["laptop", "internet_access"],
            "assessment": ["printer", "pencils"],
            "reading": ["printer"],
            "video_guide": ["computer", "internet_access", "speakers"],
            "rubric": ["printer"],
            "syllabus": ["printer"],
            "homework": ["paper", "pencils"],
        }

        rows: list[dict] = []
        texts: list[str] = []
        for _ in range(count):
            user_id, subjects, levels, methods = self.random.choices(
                owners, cum_weights=owner_cum_weights, k=1
            )[0]
            subject = self.random.choice(list(subjects) or ["mathematics"])
            level = self.random.choice(list(levels) or ["high_school"])
            method = self.random.choice(list(methods) or ["project_based"])
            resource_type = self.random.choice(list(RESOURCE_KINDS))
            topic = self.random.choice(TOPICS.get(subject, ["core concepts"]))
            difficulty = {
                "elementary": "beginner",
                "middle_school": self.random.choice(["beginner", "intermediate"]),
                "high_school": self.random.choice(["beginner", "intermediate", "advanced"]),
                "university": self.random.choice(["intermediate", "advanced"]),
                "graduate": "advanced",
                "adult_education": self.random.choice(["beginner", "intermediate"]),
            }[level]
            # Soften: middle_school advanced should be rare — already excluded.
            if level == "high_school" and difficulty == "advanced" and self.random.random() < 0.55:
                difficulty = "intermediate"
            title = self.random.choice(RESOURCE_TITLE_TEMPLATES).format(
                subject=subject.replace("_", " ").title(),
                topic=topic,
                kind=RESOURCE_KINDS[resource_type],
                level=level.replace("_", " "),
            )
            description = self.random.choice(
                [
                    (
                        f"A {RESOURCE_KINDS[resource_type]} on {topic} for "
                        f"{level.replace('_', ' ')} students, designed around "
                        f"{METHOD_PHRASES.get(method, method)}."
                    ),
                    (
                        f"Classroom-tested {RESOURCE_KINDS[resource_type]} covering {topic}. "
                        f"Built for {level.replace('_', ' ')} cohorts using a "
                        f"{method.replace('_', ' ')} arc, with teacher notes and timing."
                    ),
                    (
                        f"Plug-and-play {topic} materials ({RESOURCE_KINDS[resource_type]}). "
                        f"Includes differentiation tips and a short reflection prompt."
                    ),
                    (
                        f"Use this {RESOURCE_KINDS[resource_type]} when introducing {topic} "
                        f"to {level.replace('_', ' ')} learners. Emphasises "
                        f"{METHOD_PHRASES.get(method, method)}."
                    ),
                ]
            )
            tags = [subject, topic.split()[0].lower(), method, difficulty]
            if self.random.random() < 0.4:
                tags.append(level)
            required_materials = list(materials_by_type.get(resource_type, []))
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "owner_id": user_id,
                    "title": title[:250],
                    "description": description,
                    "resource_type": resource_type,
                    "subject": subject,
                    "education_level": level,
                    "difficulty": difficulty,
                    "teaching_method": method,
                    "tags": tags,
                    "required_materials": required_materials,
                    "file_url": None,
                    "download_count": int(self.random.paretovariate(1.4) * 8) % 2500,
                }
            )
            texts.append(
                EmbeddingService.build_resource_text(
                    title=title,
                    description=description,
                    subject=subject,
                    education_level=level,
                    teaching_method=method,
                    difficulty=difficulty,
                    tags=tags,
                    required_materials=required_materials,
                )
            )

        vectors = await self.embeddings.generate_embeddings(texts)
        for row, vector in zip(rows, vectors):
            row["embedding"] = vector
        await self._bulk_insert(Resource, rows)
        logger.info("Inserted %d resources", count)
        return count

    async def generate_ratings(self, user_ids: list[uuid.UUID], count: int) -> int:
        if len(user_ids) < 2:
            return 0
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        rows: list[dict] = []
        attempts = 0
        while len(rows) < count and attempts < count * 6:
            attempts += 1
            reviewer = user_ids[self.random.randrange(len(user_ids))]
            teacher = self._biased_peer(reviewer, user_ids)
            if reviewer == teacher or (reviewer, teacher) in seen:
                continue
            seen.add((reviewer, teacher))
            # Skewed towards positive, like every real review corpus.
            score = self.random.choices([5, 4, 3, 2, 1], weights=[48, 28, 14, 7, 3], k=1)[0]
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "reviewer_id": reviewer,
                    "teacher_id": teacher,
                    "rating": score,
                    "comment": self.random.choice(RATING_COMMENTS),
                    "is_verified_student": self.random.random() < 0.28,
                }
            )
        await self._bulk_insert(Rating, rows)
        await self.refresh_rating_rollups()
        logger.info("Inserted %d ratings", len(rows))
        return len(rows)

    async def refresh_rating_rollups(self) -> None:
        """Recompute average_rating / rating_count in one SQL statement."""
        await self.db.execute(
            text(
                """
                UPDATE teacher_profiles p
                SET average_rating = COALESCE(r.avg_rating, 0),
                    rating_count   = COALESCE(r.count_rating, 0)
                FROM (
                    SELECT teacher_id,
                           ROUND(AVG(rating)::numeric, 2) AS avg_rating,
                           COUNT(*) AS count_rating
                    FROM ratings GROUP BY teacher_id
                ) r
                WHERE p.user_id = r.teacher_id
                """
            )
        )
        await self.db.commit()

    async def generate_connections(self, user_ids: list[uuid.UUID], count: int) -> int:
        if len(user_ids) < 2:
            return 0
        statuses = [
            ConnectionStatus.ACCEPTED,
            ConnectionStatus.PENDING,
            ConnectionStatus.REJECTED,
            ConnectionStatus.BLOCKED,
        ]
        weights = [72, 20, 6, 2]
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        rows: list[dict] = []
        attempts = 0
        while len(rows) < count and attempts < count * 6:
            attempts += 1
            a = user_ids[self.random.randrange(len(user_ids))]
            b = self._biased_peer(a, user_ids)
            if a == b:
                continue
            key = (a, b) if str(a) < str(b) else (b, a)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "requester_id": key[0],
                    "receiver_id": key[1],
                    "status": self.random.choices(statuses, weights=weights, k=1)[0],
                }
            )
        await self._bulk_insert(Connection, rows)
        logger.info("Inserted %d connections", len(rows))
        return len(rows)

    async def generate_conversations(self, user_ids: list[uuid.UUID], count: int) -> tuple[int, int]:
        if len(user_ids) < 2 or count <= 0:
            return 0, 0
        conversations, participants, messages = [], [], []
        for _ in range(count):
            a = user_ids[self.random.randrange(len(user_ids))]
            b = self._biased_peer(a, user_ids)
            if a == b:
                continue
            conversation_id = uuid.uuid4()
            conversations.append({"id": conversation_id})
            participants.extend(
                [
                    {"conversation_id": conversation_id, "user_id": a},
                    {"conversation_id": conversation_id, "user_id": b},
                ]
            )
            meta = self._profile_meta.get(a, {})
            subject = self.random.choice(meta.get("subjects") or ["computer_science"])
            level = self.random.choice(meta.get("levels") or ["high_school"])
            topic = self.random.choice(TOPICS.get(subject, ["core concepts"]))
            opener = self.random.choice(MESSAGE_OPENERS).format(
                topic=topic,
                subject=subject.replace("_", " "),
                level=level.replace("_", " "),
            )
            messages.append(
                {
                    "id": uuid.uuid4(),
                    "conversation_id": conversation_id,
                    "sender_id": a,
                    "content": opener,
                }
            )
            # Most threads get 1 reply; some stretch into short back-and-forth.
            reply_count = self.random.choices([0, 1, 2, 3], weights=[15, 50, 25, 10], k=1)[0]
            sender = b
            for _ in range(reply_count):
                messages.append(
                    {
                        "id": uuid.uuid4(),
                        "conversation_id": conversation_id,
                        "sender_id": sender,
                        "content": self.random.choice(MESSAGE_REPLIES),
                    }
                )
                sender = a if sender == b else b
        await self._bulk_insert(Conversation, conversations)
        await self._bulk_insert(ConversationParticipant, participants)
        await self._bulk_insert(Message, messages)
        logger.info("Inserted %d conversations with %d messages", len(conversations), len(messages))
        return len(conversations), len(messages)

    # --- orchestration ----------------------------------------------------- #
    async def run(self, truncate: bool = True, rebuild_indexes: bool = True) -> GenerationStats:
        started = time.perf_counter()
        stats = GenerationStats()
        if truncate:
            await self.truncate()
        if rebuild_indexes:
            await self.drop_vector_indexes()

        demo_accounts = await self.create_demo_accounts()
        demo_ids = [user_id for user_id, _ in demo_accounts]
        stats.demo_accounts = [info["email"] for _, info in demo_accounts]

        user_ids = demo_ids + await self.generate_users(max(self.counts.users - len(demo_ids), 0))
        stats.users = len(user_ids)
        stats.profiles = len(user_ids)
        stats.resources = await self.generate_resources(user_ids, self.counts.resources)
        stats.ratings = await self.generate_ratings(user_ids, self.counts.ratings)
        stats.connections = await self.generate_connections(user_ids, self.counts.connections)
        stats.conversations, stats.messages = await self.generate_conversations(
            user_ids, self.counts.conversations
        )
        if rebuild_indexes:
            await self.create_vector_indexes()
        stats.seconds = round(time.perf_counter() - started, 1)
        return stats
