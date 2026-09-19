"""Teacher search: structured filters, semantic queries and geographic radius."""

from __future__ import annotations

import pytest

from tests.conftest import register_with_profile, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def seed(client) -> dict:
    boston_cs = await register_with_profile(
        client,
        first_name="Alice",
        location_name="Boston, Massachusetts",
        latitude=42.36,
        longitude=-71.06,
        education_levels=["high_school"],
        subjects=["computer_science", "python"],
        fields_of_expertise=["software_engineering"],
        teaching_levels=["beginner", "intermediate"],
        teaching_methods=["project_based"],
        teaching_style="Project-based computer science with team software builds.",
        class_size=25,
        years_experience=5,
        languages=["English"],
    )
    singapore_bio = await register_with_profile(
        client,
        first_name="Mei",
        location_name="Singapore",
        latitude=1.35,
        longitude=103.82,
        education_levels=["university"],
        subjects=["biology"],
        fields_of_expertise=["research_methods"],
        teaching_levels=["advanced"],
        teaching_methods=["lecture_based"],
        teaching_style="Lecture-based molecular biology with weekly problem sets.",
        class_size=120,
        years_experience=15,
        languages=["English", "Mandarin"],
    )
    cambridge_cs = await register_with_profile(
        client,
        first_name="Bob",
        location_name="Cambridge, Massachusetts",
        latitude=42.37,
        longitude=-71.11,
        education_levels=["high_school"],
        subjects=["computer_science"],
        fields_of_expertise=["web_development"],
        teaching_levels=["beginner"],
        teaching_methods=["project_based", "collaborative"],
        teaching_style="Project-based web development where students ship real apps.",
        class_size=28,
        years_experience=6,
        languages=["English", "Spanish"],
    )
    return {"alice": boston_cs, "mei": singapore_bio, "bob": cambridge_cs}


async def test_search_without_filters_returns_everyone_else(client):
    cohort = await seed(client)
    response = await client.get("/search/teachers", headers=cohort["alice"]["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "postgres"
    assert body["total"] == 2  # Alice is excluded from her own results
    assert {item["teacher"]["first_name"] for item in body["items"]} == {"Mei", "Bob"}


async def test_subject_filter(client):
    cohort = await seed(client)
    body = (
        await client.get("/search/teachers?subject=computer_science", headers=cohort["mei"]["headers"])
    ).json()
    assert {item["teacher"]["first_name"] for item in body["items"]} == {"Alice", "Bob"}

    empty = (
        await client.get("/search/teachers?subject=music", headers=cohort["mei"]["headers"])
    ).json()
    assert empty["total"] == 0


async def test_expertise_terms_are_canonicalised_in_filters(client):
    cohort = await seed(client)
    # 'CS' is a synonym of computer_science.
    body = (await client.get("/search/teachers?subject=CS", headers=cohort["mei"]["headers"])).json()
    assert body["total"] == 2


async def test_education_and_teaching_level_filters(client):
    cohort = await seed(client)
    hs = (
        await client.get("/search/teachers?education_level=high_school", headers=cohort["mei"]["headers"])
    ).json()
    assert {item["teacher"]["first_name"] for item in hs["items"]} == {"Alice", "Bob"}

    advanced = (
        await client.get("/search/teachers?teaching_level=advanced", headers=cohort["alice"]["headers"])
    ).json()
    assert [item["teacher"]["first_name"] for item in advanced["items"]] == ["Mei"]


async def test_teaching_method_and_class_size_filters(client):
    cohort = await seed(client)
    method = (
        await client.get("/search/teachers?teaching_method=project_based", headers=cohort["mei"]["headers"])
    ).json()
    assert {item["teacher"]["first_name"] for item in method["items"]} == {"Alice", "Bob"}

    size = (
        await client.get("/search/teachers?class_size=26", headers=cohort["mei"]["headers"])
    ).json()
    names = {item["teacher"]["first_name"] for item in size["items"]}
    assert "Alice" in names and "Bob" in names and "Mei" not in names


async def test_geographic_radius_search(client):
    cohort = await seed(client)
    near = (
        await client.get(
            "/search/teachers?latitude=42.36&longitude=-71.06&radius_km=25",
            headers=cohort["mei"]["headers"],
        )
    ).json()
    assert {item["teacher"]["first_name"] for item in near["items"]} == {"Alice", "Bob"}
    for item in near["items"]:
        assert item["distance_km"] is not None and item["distance_km"] <= 25

    tiny = (
        await client.get(
            "/search/teachers?latitude=42.36&longitude=-71.06&radius_km=2",
            headers=cohort["mei"]["headers"],
        )
    ).json()
    assert [item["teacher"]["first_name"] for item in tiny["items"]] == ["Alice"]


async def test_distance_sort(client):
    cohort = await seed(client)
    body = (
        await client.get(
            "/search/teachers?latitude=42.36&longitude=-71.06&radius_km=20000&sort=distance",
            headers=cohort["mei"]["headers"],
        )
    ).json()
    distances = [item["distance_km"] for item in body["items"]]
    assert distances == sorted(distances)


async def test_semantic_query_ranks_by_meaning(client):
    cohort = await seed(client)
    # Searching as Alice: Bob (project-based CS) must outrank Mei (lecture biology).
    body = (
        await client.get(
            "/search/teachers?query=students building real software projects in teams",
            headers=cohort["alice"]["headers"],
        )
    ).json()
    names = [item["teacher"]["first_name"] for item in body["items"]]
    assert names[0] == "Bob"
    assert names[-1] == "Mei"
    assert all(0.0 <= item["score"] <= 1.0 for item in body["items"])


async def test_minimum_rating_filter(client):
    cohort = await seed(client)
    await client.post(
        f"/teachers/{cohort['bob']['user_id']}/ratings",
        json={"rating": 5, "comment": "Fantastic collaborator."},
        headers=cohort["alice"]["headers"],
    )
    body = (
        await client.get("/search/teachers?minimum_rating=4.5", headers=cohort["mei"]["headers"])
    ).json()
    assert [item["teacher"]["first_name"] for item in body["items"]] == ["Bob"]


async def test_language_and_experience_filters(client):
    cohort = await seed(client)
    spanish = (
        await client.get("/search/teachers?language=Spanish", headers=cohort["mei"]["headers"])
    ).json()
    assert [item["teacher"]["first_name"] for item in spanish["items"]] == ["Bob"]

    senior = (
        await client.get("/search/teachers?min_years_experience=10", headers=cohort["alice"]["headers"])
    ).json()
    assert [item["teacher"]["first_name"] for item in senior["items"]] == ["Mei"]


async def test_pagination(client):
    cohort = await seed(client)
    page = (
        await client.get("/search/teachers?limit=1&offset=0", headers=cohort["alice"]["headers"])
    ).json()
    assert len(page["items"]) == 1
    assert page["total"] == 2
    assert page["limit"] == 1 and page["offset"] == 0


async def test_search_is_public(client):
    await seed(client)
    response = await client.get("/search/teachers")
    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_engine_status_endpoint(client):
    response = await client.get("/search/engine")
    assert response.status_code == 200
    assert response.json()["provider"] == "postgres"
