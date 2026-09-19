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

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import Connection, ConnectionStatus
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.recommendation import RecommendationEvent
from app.models.resource import Resource
from app.models.user import User
from app.services.embedding_service import EmbeddingService, HashingEmbeddingProvider
from app.utils.auth import hash_password

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "DemoPassword123!"

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
CITIES: list[tuple[str, float, float, list[str]]] = [
    ("Boston, Massachusetts", 42.36, -71.06, ["English"]),
    ("Cambridge, Massachusetts", 42.37, -71.11, ["English"]),
    ("New York, New York", 40.71, -74.01, ["English", "Spanish"]),
    ("Toronto, Ontario", 43.65, -79.38, ["English", "French"]),
    ("Edmonton, Alberta", 53.55, -113.49, ["English", "French"]),
    ("San Francisco, California", 37.77, -122.42, ["English", "Mandarin"]),
    ("Seattle, Washington", 47.61, -122.33, ["English"]),
    ("London, United Kingdom", 51.51, -0.13, ["English"]),
    ("Dubai, United Arab Emirates", 25.20, 55.27, ["English", "Arabic"]),
    ("Singapore", 1.35, 103.82, ["English", "Mandarin", "Malay"]),
    ("Tashkent, Uzbekistan", 41.30, 69.24, ["Uzbek", "Russian", "English"]),
]

# Subjects that make sense at each education level, with the expertise terms
# and typical class sizes that go with them.
LEVEL_PROFILES: dict[str, dict] = {
    "elementary": {
        "subjects": ["mathematics", "english", "art", "music", "biology"],
        "expertise": ["literacy", "numeracy", "classroom_management", "social_emotional_learning"],
        "class_size": (18, 30),
        "levels": ["beginner"],
        "institution_types": ["public_school", "private_school", "charter_school"],
    },
    "middle_school": {
        "subjects": ["mathematics", "english", "history", "biology", "computer_science", "art"],
        "expertise": ["project_design", "differentiation", "stem_outreach", "literacy"],
        "class_size": (20, 32),
        "levels": ["beginner", "intermediate"],
        "institution_types": ["public_school", "charter_school", "private_school"],
    },
    "high_school": {
        "subjects": [
            "mathematics",
            "physics",
            "chemistry",
            "biology",
            "computer_science",
            "english",
            "history",
            "economics",
            "statistics",
            "engineering",
        ],
        "expertise": [
            "software_engineering",
            "robotics",
            "lab_design",
            "exam_preparation",
            "curriculum_design",
            "python",
        ],
        "class_size": (18, 35),
        "levels": ["beginner", "intermediate", "advanced"],
        "institution_types": ["public_school", "private_school", "charter_school"],
    },
    "university": {
        "subjects": [
            "computer_science",
            "artificial_intelligence",
            "machine_learning",
            "mathematics",
            "physics",
            "economics",
            "business",
            "psychology",
            "statistics",
            "engineering",
        ],
        "expertise": [
            "machine_learning",
            "data_science",
            "research_methods",
            "software_engineering",
            "academic_writing",
        ],
        "class_size": (30, 120),
        "levels": ["intermediate", "advanced"],
        "institution_types": ["university", "community_college"],
    },
    "graduate": {
        "subjects": [
            "machine_learning",
            "artificial_intelligence",
            "physics",
            "statistics",
            "psychology",
            "engineering",
            "economics",
        ],
        "expertise": [
            "research_methods",
            "quantum_computing",
            "deep_learning",
            "thesis_supervision",
            "grant_writing",
        ],
        "class_size": (8, 30),
        "levels": ["advanced"],
        "institution_types": ["university"],
    },
    "adult_education": {
        "subjects": ["english", "business", "computer_science", "mathematics", "art"],
        "expertise": ["career_transition", "esl", "workplace_training", "programming"],
        "class_size": (10, 25),
        "levels": ["beginner", "intermediate"],
        "institution_types": ["community_college", "online_academy", "nonprofit", "independent"],
    },
}

METHOD_PHRASES: dict[str, str] = {
    "project_based": "students build real projects end to end",
    "lecture_based": "clear structured lectures with worked examples",
    "collaborative": "small teams that critique and improve each other's work",
    "socratic": "questioning that pushes students to justify their reasoning",
    "hands_on": "manipulatives, labs and physical builds",
    "flipped_classroom": "content at home, practice and feedback in class",
    "inquiry_based": "students investigate open questions and design experiments",
    "game_based": "gameplay loops and friendly competition",
    "discussion_based": "seminar-style discussion and debate",
    "problem_based": "messy real-world problems as the organising unit",
}

RESOURCE_TITLE_TEMPLATES = [
    "{subject} {topic}: {kind}",
    "{topic} - a {level} {kind}",
    "{kind} for teaching {topic}",
    "{subject} unit: {topic}",
]
RESOURCE_KINDS = {
    "lesson_plan": "lesson plan",
    "worksheet": "worksheet",
    "slide_deck": "slide deck",
    "assessment": "assessment",
    "project_brief": "project brief",
    "reading": "reading pack",
    "video_guide": "video guide",
    "rubric": "rubric",
}
TOPICS: dict[str, list[str]] = {
    "mathematics": ["fractions", "quadratics", "vectors", "probability", "geometry proofs"],
    "physics": ["kinematics", "circuits", "waves", "thermodynamics", "optics"],
    "chemistry": ["stoichiometry", "acids and bases", "periodic trends", "reaction rates"],
    "biology": ["cell division", "genetics", "ecosystems", "photosynthesis"],
    "computer_science": ["functions", "recursion", "data structures", "web apps", "debugging"],
    "english": ["persuasive writing", "close reading", "poetry analysis", "narrative craft"],
    "history": ["primary sources", "industrial revolution", "civil rights", "world war one"],
    "economics": ["supply and demand", "elasticity", "market failure", "game theory"],
    "business": ["business models", "pitching", "market research", "financial literacy"],
    "art": ["colour theory", "portfolio building", "printmaking", "digital illustration"],
    "music": ["rhythm training", "ensemble skills", "music theory", "composition"],
    "engineering": ["CAD basics", "bridge design", "materials testing", "prototyping"],
    "psychology": ["research ethics", "memory", "developmental stages", "bias"],
    "statistics": ["hypothesis testing", "regression", "sampling", "data visualisation"],
    "artificial_intelligence": ["search algorithms", "ethics of AI", "prompting", "agents"],
    "machine_learning": ["train/test splits", "overfitting", "neural networks", "embeddings"],
    "literacy": ["phonics", "reading fluency", "vocabulary building"],
    "numeracy": ["number sense", "mental maths", "place value"],
    "python": ["loops", "list comprehensions", "unit testing", "APIs"],
    "robotics": ["line following", "sensor calibration", "gear ratios"],
}


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

    # --- helpers ---------------------------------------------------------- #
    def _password_hash(self, password: str = DEMO_PASSWORD) -> str:
        """Hash once and reuse: Argon2 is deliberately slow, and this is fake data."""
        if password not in self._hasher_cache:
            self._hasher_cache[password] = hash_password(password)
        return self._hasher_cache[password]

    def _teaching_style_text(self, methods: list[str], subjects: list[str], level: str) -> str:
        phrases = [METHOD_PHRASES[m] for m in methods]
        subject_text = subjects[0].replace("_", " ")
        lead = self.random.choice(
            [
                f"I teach {subject_text} through {phrases[0]}",
                f"My {subject_text} classroom runs on {phrases[0]}",
                f"I lean on {phrases[0]} when teaching {subject_text}",
            ]
        )
        if len(phrases) > 1:
            lead += f", supported by {phrases[1]}"
        tail = self.random.choice(
            [
                "Assessment is mostly formative, with plenty of peer feedback.",
                "Every unit ends with something students can show to a real audience.",
                "I plan backwards from the skill I want students to walk out with.",
                "I care more about students explaining their thinking than final answers.",
            ]
        )
        return f"{lead}. {tail}"

    def _bio_text(self, years: int, level: str, subjects: list[str], institution: str) -> str:
        subject_text = " and ".join(s.replace("_", " ") for s in subjects[:2])
        level_text = level.replace("_", " ")
        return self.random.choice(
            [
                f"{years} years teaching {subject_text} at {level_text} level. Currently at {institution}.",
                f"{level_text.capitalize()} {subject_text} teacher at {institution}, {years} years in the classroom.",
                f"I have spent {years} years building {subject_text} curricula "
                f"for {level_text} students at {institution}.",
            ]
        )

    def _institution_name(self, level: str, city: str) -> str:
        town = city.split(",")[0]
        if level in ("university", "graduate"):
            return self.random.choice(
                [f"University of {town}", f"{town} Institute of Technology", f"{town} State University"]
            )
        if level == "adult_education":
            return self.random.choice([f"{town} Community College", f"{town} Learning Hub"])
        return self.random.choice(
            [f"{town} High School", f"{town} Academy", f"{town} Preparatory School", f"{town} School"]
        )

    def _make_profile_payload(self, level: str, city_index: int | None = None) -> dict:
        spec = LEVEL_PROFILES[level]
        city, lat, lon, languages = CITIES[
            city_index if city_index is not None else self.random.randrange(len(CITIES))
        ]
        subjects = self.random.sample(spec["subjects"], k=self.random.randint(1, 3))
        expertise = self.random.sample(spec["expertise"], k=self.random.randint(1, 3))
        methods = self.random.sample(list(METHOD_PHRASES), k=self.random.randint(1, 3))
        teaching_levels = self.random.sample(
            spec["levels"], k=self.random.randint(1, len(spec["levels"]))
        )
        institution = self._institution_name(level, city)
        years = self.random.randint(1, 30)
        return {
            "education_levels": [level],
            "subjects": subjects,
            "fields_of_expertise": expertise,
            "teaching_methods": methods,
            "teaching_levels": teaching_levels,
            "teaching_style": self._teaching_style_text(methods, subjects, level),
            "bio": self._bio_text(years, level, subjects, institution),
            "class_size": self.random.randint(*spec["class_size"]),
            "years_experience": years,
            "languages": languages[: self.random.randint(1, len(languages))],
            "institution": institution,
            "institution_type": self.random.choice(spec["institution_types"]),
            "location_name": city,
            # Jitter within a city so proximity scoring has something to chew on.
            "latitude": round(lat + self.random.uniform(-0.12, 0.12), 2),
            "longitude": round(lon + self.random.uniform(-0.12, 0.12), 2),
        }

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
                        "Project-based, collaborative and hands-on. My students build real "
                        "software in small teams and demo it to an audience every term."
                    ),
                    "bio": "I teach computer science using project-based learning.",
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
                        "Project-based and collaborative. Students work in pairs to ship a "
                        "working app each unit, with peer code review built into the process."
                    ),
                    "bio": "High school computer science teacher who runs everything as a project.",
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
                    "teaching_methods": ["lecture_based"],
                    "teaching_levels": ["advanced"],
                    "teaching_style": (
                        "Lecture-based with formal problem sets. I cover the mathematics of "
                        "machine learning carefully before any implementation work."
                    ),
                    "bio": "Associate professor teaching machine learning to undergraduates.",
                    "class_size": 90,
                    "years_experience": 12,
                    "languages": ["English"],
                    "institution": "University of New York",
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
                        "Hands-on and project-based: every physics concept arrives through a "
                        "build, a measurement and an argument about the data."
                    ),
                    "bio": "Physics and engineering teacher running a school robotics programme.",
                    "class_size": 24,
                    "years_experience": 8,
                    "languages": ["English"],
                    "institution": "Somerville High School",
                    "institution_type": "public_school",
                    "location_name": "Boston, Massachusetts",
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
        password_hash = self._password_hash()
        levels = list(LEVEL_PROFILES)
        weights = [0.16, 0.16, 0.30, 0.22, 0.08, 0.08]  # more high school + university

        user_ids: list[uuid.UUID] = []
        user_rows: list[dict] = []
        profile_rows: list[dict] = []
        texts: list[str] = []
        pending_profiles: list[dict] = []

        for index in range(count):
            user_id = uuid.uuid4()
            user_ids.append(user_id)
            first, last = faker.first_name(), faker.last_name()
            user_rows.append(
                {
                    "id": user_id,
                    "email": f"teacher{index}@edumatch.demo",
                    "password_hash": password_hash,
                    "first_name": first,
                    "last_name": last,
                    "is_verified": self.random.random() < 0.35,
                    "is_active": True,
                }
            )
            level = self.random.choices(levels, weights=weights, k=1)[0]
            profile = self._make_profile_payload(level)
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
        """Resources consistent with their owner's subjects and level."""
        owners = (
            await self.db.execute(
                select(
                    TeacherProfile.user_id,
                    TeacherProfile.subjects,
                    TeacherProfile.education_levels,
                    TeacherProfile.teaching_methods,
                )
            )
        ).all()
        if not owners:
            return 0

        rows: list[dict] = []
        texts: list[str] = []
        for _ in range(count):
            user_id, subjects, levels, methods = owners[self.random.randrange(len(owners))]
            subject = self.random.choice(list(subjects) or ["mathematics"])
            level = self.random.choice(list(levels) or ["high_school"])
            method = self.random.choice(list(methods) or ["project_based"])
            resource_type = self.random.choice(list(RESOURCE_KINDS))
            topic = self.random.choice(TOPICS.get(subject, ["core concepts"]))
            difficulty = {
                "elementary": "beginner",
                "middle_school": "beginner",
                "high_school": self.random.choice(["beginner", "intermediate"]),
                "university": self.random.choice(["intermediate", "advanced"]),
                "graduate": "advanced",
                "adult_education": self.random.choice(["beginner", "intermediate"]),
            }[level]
            title = self.random.choice(RESOURCE_TITLE_TEMPLATES).format(
                subject=subject.replace("_", " ").title(),
                topic=topic,
                kind=RESOURCE_KINDS[resource_type],
                level=level.replace("_", " "),
            )
            description = (
                f"A {RESOURCE_KINDS[resource_type]} on {topic} for {level.replace('_', ' ')} "
                f"students, designed around {METHOD_PHRASES[method]}."
            )
            tags = [subject, topic.split()[0].lower(), method]
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
                    "file_url": None,
                    "download_count": self.random.randint(0, 500),
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
        comments = [
            "Generous with materials and quick to answer questions.",
            "We co-planned a unit together - clear thinker, great with scaffolding.",
            "Her project briefs saved me a fortnight of planning.",
            "Ran a workshop for our department that actually changed how we teach.",
            "Helpful, but the resources needed some adapting for my class.",
            "Excellent at assessment design.",
            None,
        ]
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        rows: list[dict] = []
        attempts = 0
        while len(rows) < count and attempts < count * 4:
            attempts += 1
            reviewer = user_ids[self.random.randrange(len(user_ids))]
            teacher = user_ids[self.random.randrange(len(user_ids))]
            if reviewer == teacher or (reviewer, teacher) in seen:
                continue
            seen.add((reviewer, teacher))
            # Skewed towards positive, like every real review corpus.
            score = self.random.choices([5, 4, 3, 2, 1], weights=[45, 30, 15, 7, 3], k=1)[0]
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "reviewer_id": reviewer,
                    "teacher_id": teacher,
                    "rating": score,
                    "comment": self.random.choice(comments),
                    "is_verified_student": self.random.random() < 0.3,
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
        weights = [70, 22, 6, 2]
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        rows: list[dict] = []
        attempts = 0
        while len(rows) < count and attempts < count * 4:
            attempts += 1
            a = user_ids[self.random.randrange(len(user_ids))]
            b = user_ids[self.random.randrange(len(user_ids))]
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
        openers = [
            "Hi! We seem to teach the same unit - fancy swapping materials?",
            "Your project brief looked great. How long do students spend on it?",
            "Would you be up for co-running a workshop next term?",
            "How do you handle assessment for group projects?",
        ]
        replies = [
            "Absolutely - I'll send over what I use this week.",
            "Happy to chat. Mine runs across three weeks including the demo day.",
            "Yes! Let me check with my department head and get back to you.",
        ]
        conversations, participants, messages = [], [], []
        for _ in range(count):
            a = user_ids[self.random.randrange(len(user_ids))]
            b = user_ids[self.random.randrange(len(user_ids))]
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
            messages.append(
                {
                    "id": uuid.uuid4(),
                    "conversation_id": conversation_id,
                    "sender_id": a,
                    "content": self.random.choice(openers),
                }
            )
            if self.random.random() < 0.7:
                messages.append(
                    {
                        "id": uuid.uuid4(),
                        "conversation_id": conversation_id,
                        "sender_id": b,
                        "content": self.random.choice(replies),
                    }
                )
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
