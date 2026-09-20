#!/usr/bin/env python
"""Seed concept vocabulary (OCW-style) and technique demo data.

Examples
--------
    python scripts/seed_technique_demo.py
    python scripts/seed_technique_demo.py --judge-email judge@edumatch.demo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal, ensure_extensions
from app.models.class_profile import ClassProfile
from app.models.concept import Concept
from app.models.technique import Technique, TechniqueConcept, TechniqueRating
from app.models.user import User
from app.services import concept_service
from app.services.technique_search_service import refresh_technique_embedding
from app.utils.auth import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("seed-technique-demo")

# Deep seed: 2–3 subjects, 50–100 concepts each (OCW-inspired topic lists).
SUBJECT_CONCEPTS: dict[str, list[str]] = {
    "calculus": [
        "Limits", "One-sided limits", "Continuity", "Intermediate value theorem",
        "Derivatives", "Difference quotient", "Power rule", "Product rule",
        "Quotient rule", "Chain rule", "Implicit differentiation", "Related rates",
        "Linear approximation", "Differentials", "Extreme values", "Mean value theorem",
        "First derivative test", "Second derivative test", "Concavity", "Optimization",
        "Newton's method", "Antiderivatives", "Indefinite integrals", "Definite integrals",
        "Fundamental theorem of calculus", "Substitution", "Integration by parts",
        "Partial fractions", "Improper integrals", "Area between curves",
        "Volumes of solids of revolution", "Arc length", "Sequences", "Series",
        "Geometric series", "Integral test", "Comparison test", "Ratio test",
        "Alternating series", "Power series", "Taylor series", "Maclaurin series",
        "Radius of convergence", "Parametric equations", "Polar coordinates",
        "Differential equations", "Separable equations", "Slope fields",
        "Euler's method", "Exponential growth", "Logarithmic differentiation",
        "Inverse functions", "Inverse trig derivatives", "Hyperbolic functions",
        "L'Hôpital's rule", "Absolute extrema", "Critical points", "Inflection points",
        "Riemann sums", "Average value of a function", "Work integrals",
        "Center of mass", "Probability density integrals", "Arc length parametric",
        "Surface area of revolution", "Comparison of improper integrals",
        "Root test", "Absolute vs conditional convergence", "Fourier intuition",
        "Multivariable preview", "Partial derivatives preview", "Gradient preview",
        "Directional derivatives preview", "Lagrange multipliers preview",
        "Vector-valued functions", "Curvature", "Motion in the plane",
        "Projectile motion calculus", "Related rates geometry", "Optimization economics",
        "Optimization biology", "Logistic growth", "Separable mixing problems",
        "Exact equations preview", "Numerical integration", "Trapezoid rule",
        "Simpson's rule", "Error bounds", "Series remainder estimates",
        "Binomial series", "Applications of Taylor polynomials",
    ],
    "intro_cs": [
        "Variables", "Types", "Expressions", "Conditionals", "Loops", "Functions",
        "Scope", "Recursion", "Lists", "Tuples", "Dictionaries", "Sets",
        "Mutability", "Aliasing", "Strings", "File I/O", "Exceptions",
        "Testing", "Debugging", "Complexity intuition", "Big-O basics",
        "Linear search", "Binary search", "Sorting intuition", "Selection sort",
        "Insertion sort", "Merge sort", "Hashing intuition", "Stacks", "Queues",
        "Linked lists", "Trees", "Binary trees", "Tree traversals", "Graphs intro",
        "BFS", "DFS", "Object-oriented basics", "Classes", "Inheritance",
        "Encapsulation", "Interfaces", "Modules", "Packages", "APIs",
        "JSON", "HTTP basics", "Client-server", "Databases intro", "SQL select",
        "SQL join", "Transactions intuition", "Concurrency intro", "Race conditions",
        "Locks", "Memory model intuition", "Pointers vs references", "Stacks vs heaps",
        "Garbage collection", "Immutable data", "Pure functions", "Side effects",
        "Map filter reduce", "List comprehensions", "Generators", "Iterators",
        "Regular expressions", "Parsing basics", "Grammars intuition",
        "Finite automata intuition", "Version control", "Code review",
        "Design by contract", "Assertions", "Property-based testing",
        "Mocking", "Refactoring", "Naming", "Decomposition", "Abstraction",
        "Information hiding", "Software architecture intro", "MVC intuition",
        "REST resources", "Authentication basics", "Security basics",
        "Input validation", "Off-by-one errors", "Floating point pitfalls",
        "Integer overflow", "Null vs optional", "Error handling strategies",
        "Logging", "Profiling", "Caching intuition", "Idempotency",
        "Event-driven programming", "Callbacks", "Async intuition",
        "Message queues intro", "Data serialization",
    ],
    "intro_biology": [
        "Scientific method", "Cell theory", "Prokaryotes", "Eukaryotes",
        "Organelles", "Plasma membrane", "Membrane transport", "Osmosis",
        "Diffusion", "Endomembrane system", "Mitochondria", "Chloroplasts",
        "Cytoskeleton", "Extracellular matrix", "Cell cycle", "Mitosis",
        "Meiosis", "DNA structure", "Chromosomes", "Replication",
        "Transcription", "Translation", "Genetic code", "Mutations",
        "Gene regulation", "Operons", "Epigenetics intro", "Mendelian genetics",
        "Punnett squares", "Independent assortment", "Linkage", "Pedigrees",
        "Hardy-Weinberg", "Natural selection", "Speciation", "Phylogeny",
        "Homology", "Convergent evolution", "Population ecology", "Community ecology",
        "Ecosystems", "Energy flow", "Biogeochemical cycles", "Photosynthesis",
        "Light reactions", "Calvin cycle", "Cellular respiration", "Glycolysis",
        "Krebs cycle", "Electron transport chain", "Fermentation", "Enzymes",
        "Enzyme kinetics", "ATP", "Macromolecules", "Proteins", "Carbohydrates",
        "Lipids", "Nucleic acids", "Water properties", "pH", "Buffers",
        "Signaling pathways", "Hormones", "Nervous system intro", "Action potentials",
        "Immune system intro", "Innate immunity", "Adaptive immunity",
        "Antibodies", "Vaccines", "Microbiome", "Viruses", "Bacteria",
        "Antibiotics", "Plant structure", "Transpiration", "Animal physiology intro",
        "Homeostasis", "Feedback loops", "Development", "Stem cells",
        "Cancer biology intro", "CRISPR intro", "Biotechnology ethics",
        "Climate and biology", "Conservation biology", "Invasive species",
        "Food webs", "Keystone species", "Symbiosis", "Parasitism",
        "Commensalism", "Mutualism", "Life history strategies",
    ],
}

PROBLEM_TYPES = [
    "misconception",
    "missing_prerequisite",
    "engagement",
    "pacing",
    "transfer",
]

STYLES = [
    "inquiry",
    "worked_examples",
    "peer_instruction",
    "lab_station",
    "think_pair_share",
    "deliberate_practice",
    "socratic",
    "project_based",
]

TECHNIQUE_TEMPLATES = [
    {
        "title": "Predict–reveal–revise for {concept}",
        "summary": "Students commit to a prediction about {concept}, see a short reveal, then revise with evidence.",
        "steps": (
            "1. Pose a concrete prediction prompt about {concept}.\n"
            "2. Students write silently (1 min).\n"
            "3. Reveal a counterexample or demo.\n"
            "4. Pair revise explanations.\n"
            "5. Harvest 2 revised models on the board."
        ),
        "materials": "Mini-whiteboard or index cards; one demo slide",
        "minutes": 15,
        "types": ["misconception", "engagement"],
    },
    {
        "title": "Prerequisite warm-up ladder for {concept}",
        "summary": "A 3-rung ladder that surfaces missing skills before {concept} is introduced.",
        "steps": (
            "1. Rung A: 60-second skill check.\n"
            "2. Rung B: peer teach the weak step.\n"
            "3. Rung C: apply the skill inside a {concept} micro-task.\n"
            "4. Exit ticket tags which rung still feels shaky."
        ),
        "materials": "Printed ladder half-sheets",
        "minutes": 12,
        "types": ["missing_prerequisite", "pacing"],
    },
    {
        "title": "Transfer clinic: {concept} in a new costume",
        "summary": "Same underlying {concept}, three surface forms — students map the invariant.",
        "steps": (
            "1. Show version A (familiar).\n"
            "2. Show version B (new context).\n"
            "3. Students list what stayed constant.\n"
            "4. Version C is an exam-style prompt done in pairs.\n"
            "5. Debrief the transfer moves."
        ),
        "materials": "Three short prompts on one slide",
        "minutes": 20,
        "types": ["transfer", "engagement"],
    },
    {
        "title": "Pace-split stations on {concept}",
        "summary": "Fast and slow tracks so finishers deepen {concept} while others consolidate.",
        "steps": (
            "1. Core station (everyone).\n"
            "2. Stretch station unlocks after a check.\n"
            "3. Support station with worked skeleton.\n"
            "4. 3-minute gallery of one insight per station."
        ),
        "materials": "Station cards; answer key folder",
        "minutes": 25,
        "types": ["pacing", "engagement"],
    },
    {
        "title": "Misconception autopsy: {concept}",
        "summary": "Students diagnose a wrong explanation of {concept} and rewrite it.",
        "steps": (
            "1. Present a plausible wrong solution.\n"
            "2. Individuals mark the first broken step.\n"
            "3. Groups rewrite the explanation.\n"
            "4. Compare to a expert model.\n"
            "5. Write a one-line 'watch out for…'."
        ),
        "materials": "Wrong-solution handout",
        "minutes": 18,
        "types": ["misconception", "transfer"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed concepts + techniques for demo")
    parser.add_argument("--judge-email", default="judge@edumatch.demo")
    parser.add_argument("--judge-password", default="JudgeDemo2026!")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--techniques-per-subject",
        type=int,
        default=40,
        help="Varied techniques generated per subject",
    )
    return parser.parse_args()


async def ensure_judge(db, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name="Demo",
            last_name="Judge",
            is_verified=True,
        )
        db.add(user)
        await db.flush()
        logger.info("Created judge account %s", email)
    return user


async def ensure_judge_class(db, teacher: User) -> ClassProfile:
    existing = await db.scalar(
        select(ClassProfile).where(
            ClassProfile.teacher_id == teacher.id,
            ClassProfile.title == "Calc I — Judge Demo Section",
        )
    )
    if existing:
        return existing
    row = ClassProfile(
        teacher_id=teacher.id,
        title="Calc I — Judge Demo Section",
        subject="calculus",
        level="university",
        format="lecture",
        status="active",
        class_size=32,
        student_background="First-year STEM; mixed calc AP exposure",
        constraints="50-minute periods; no clickers; whiteboard + projector",
        class_length_minutes=50,
        technology="LMS homework; Desmos optional",
        notes="Prefill for live demo: syllabus ingest + vague query follow-up",
    )
    db.add(row)
    await db.flush()
    return row


async def seed_concepts(db) -> dict[str, list[Concept]]:
    by_subject: dict[str, list[Concept]] = {}
    for subject, labels in SUBJECT_CONCEPTS.items():
        concepts: list[Concept] = []
        for label in labels:
            concept = await concept_service.canonicalize(
                db, label=label, subject=subject, use_llm_borderline=False
            )
            concepts.append(concept)
        by_subject[subject] = concepts
        logger.info("Subject %s: %d concepts", subject, len(concepts))
    await db.commit()
    return by_subject


async def seed_techniques(
    db,
    *,
    owner: User,
    by_subject: dict[str, list[Concept]],
    per_subject: int,
    rng: random.Random,
) -> int:
    created = 0
    for subject, concepts in by_subject.items():
        for i in range(per_subject):
            concept = concepts[i % len(concepts)]
            template = TECHNIQUE_TEMPLATES[i % len(TECHNIQUE_TEMPLATES)]
            # Light variation so cards aren't identical clones.
            style = STYLES[i % len(STYLES)]
            title = template["title"].format(concept=concept.label)
            if i // len(TECHNIQUE_TEMPLATES) > 0:
                title = f"{title} (variant {i // len(TECHNIQUE_TEMPLATES) + 1})"
            tech = Technique(
                owner_id=owner.id,
                title=title[:250],
                summary=template["summary"].format(concept=concept.label),
                steps=template["steps"].format(concept=concept.label),
                materials=template["materials"],
                class_time_minutes=template["minutes"] + rng.randint(-3, 5),
                teaching_style=style,
                context_subject=subject,
                context_level=rng.choice(["university", "community_college", "high_school"]),
                context_format=rng.choice(["lecture", "lab", "hybrid", "online"]),
                context_class_size=rng.choice([18, 24, 30, 40, 60, 90]),
                context_notes=f"Used while teaching {concept.label}",
                problem_types=list(template["types"]),
                is_draft=False,
                is_published=True,
            )
            db.add(tech)
            await db.flush()
            db.add(TechniqueConcept(technique_id=tech.id, concept_id=concept.id))
            # Secondary concept occasionally.
            if rng.random() < 0.35:
                other = concepts[(i + 7) % len(concepts)]
                if other.id != concept.id:
                    db.add(TechniqueConcept(technique_id=tech.id, concept_id=other.id))
            await refresh_technique_embedding(db, tech)

            # Fake student-verified ratings with varied class contexts.
            n_ratings = rng.randint(0, 38) if i % 7 != 0 else 0  # some unrated
            for _ in range(n_ratings):
                score = rng.choices([5, 4, 3, 2, 1], weights=[40, 30, 15, 10, 5])[0]
                db.add(
                    TechniqueRating(
                        technique_id=tech.id,
                        rating=score,
                        comment=rng.choice(
                            [
                                "Finally clicked after the revise step.",
                                "Took longer than posted but worth it.",
                                "Helped the quiet students speak up.",
                                None,
                                "Worked better in the smaller section.",
                            ]
                        ),
                        context_subject=subject,
                        context_level=rng.choice(
                            ["university", "community_college", "high_school"]
                        ),
                        context_format=rng.choice(["lecture", "lab", "hybrid"]),
                        context_class_size=rng.choice([20, 28, 32, 45, 80]),
                    )
                )
            if n_ratings:
                tech.rating_count = n_ratings
                # Will be approximate; fine for demo aggregates.
                tech.average_rating = float(
                    rng.uniform(3.2, 4.8) if n_ratings else 0.0
                )
            created += 1
        await db.commit()
        logger.info("Subject %s: %d techniques", subject, per_subject)
    return created


async def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    await ensure_extensions()
    async with SessionLocal() as db:
        judge = await ensure_judge(db, args.judge_email, args.judge_password)
        await ensure_judge_class(db, judge)
        await db.commit()

        by_subject = await seed_concepts(db)
        count = await seed_techniques(
            db,
            owner=judge,
            by_subject=by_subject,
            per_subject=args.techniques_per_subject,
            rng=rng,
        )
        logger.info(
            "Done. Judge login: %s / %s — techniques=%d",
            args.judge_email,
            args.judge_password,
            count,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
