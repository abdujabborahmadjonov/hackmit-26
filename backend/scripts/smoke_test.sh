#!/usr/bin/env bash
#
# End-to-end smoke test against a *running* EduMatch API. This is what CI runs
# after `docker compose up`, and it is the same thing you want to run before a
# demo:
#
#     docker compose up -d --build
#     docker compose exec -T backend python scripts/generate_demo_data.py --scale 0.02
#     scripts/smoke_test.sh
#
# Environment: BASE_URL, SMOKE_EMAIL, SMOKE_PASSWORD, HEALTH_RETRIES.
#
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SMOKE_EMAIL="${SMOKE_EMAIL:-demo_teacher@example.com}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-DemoPassword123!}"
HEALTH_RETRIES="${HEALTH_RETRIES:-60}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$1" >&2; exit 1; }

# Pipe a JSON body into a python assertion snippet: assert_json '<code>' <<< "$body"
assert_json() { python3 -c "
import json, sys
body = json.load(sys.stdin)
$1
" || fail "assertion failed: $2"; }

# --------------------------------------------------------------------------- #
step "Waiting for ${BASE_URL}/health"
healthy=false
for attempt in $(seq 1 "$HEALTH_RETRIES"); do
    if curl -fsS "${BASE_URL}/health" -o /tmp/edumatch-health.json 2>/dev/null; then
        healthy=true
        cat /tmp/edumatch-health.json
        break
    fi
    printf '  attempt %s/%s ...\n' "$attempt" "$HEALTH_RETRIES"
    sleep 2
done
[ "$healthy" = true ] || fail "the API never became healthy at ${BASE_URL}"

# --------------------------------------------------------------------------- #
step "OpenAPI schema is served"
curl -fsS "${BASE_URL}/openapi.json" | assert_json '
paths = body["paths"]
assert len(paths) > 20, f"only {len(paths)} paths in the schema"
for required in ("/auth/login", "/recommendations", "/search/teachers"):
    assert required in paths, f"{required} missing from the OpenAPI schema"
print(f"  {len(paths)} paths documented")
' "openapi.json"

# --------------------------------------------------------------------------- #
step "Logging in as ${SMOKE_EMAIL}"
login_body=$(curl -fsS -X POST "${BASE_URL}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\"}") \
    || fail "login request failed (did you seed the demo data?)"
TOKEN=$(printf '%s' "$login_body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
[ -n "$TOKEN" ] || fail "login returned no access token"
AUTH="Authorization: Bearer ${TOKEN}"
printf '  token acquired\n'

step "Wrong password is rejected"
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"definitely-not-the-password\"}")
[ "$status" = "401" ] || fail "expected 401 for a bad password, got ${status}"

step "Protected routes reject anonymous callers"
status=$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/recommendations")
[ "$status" = "401" ] || [ "$status" = "403" ] || fail "expected 401/403 without a token, got ${status}"

# --------------------------------------------------------------------------- #
step "Profile of the logged-in teacher"
curl -fsS "${BASE_URL}/profiles/me" -H "$AUTH" | assert_json '
assert body["user_id"], "profile has no user_id"
assert body["subjects"], "profile has no subjects"
assert "password_hash" not in json.dumps(body), "a password hash leaked into the payload"
subjects = ", ".join(body["subjects"])
location = body["location_name"]
print(f"  {location} / {subjects}")
' "/profiles/me"

# --------------------------------------------------------------------------- #
step "Recommendations come back scored and explained"
recs=$(curl -fsS "${BASE_URL}/recommendations?limit=5&mmr=false" -H "$AUTH")
printf '%s' "$recs" | assert_json '
items = body["items"]
assert items, "no recommendations returned"
top = items[0]
score = top["match_score"]
assert 0.0 <= score <= 1.0, f"match_score out of range: {score}"
assert top["reasons"], "the top recommendation has no reasons"
assert top["explanation"], "the top recommendation has no explanation breakdown"
assert "social" in top["components"] or "quality" in top["components"] or len(top["components"]) >= 6, (
    f"expected expanded component breakdown, got {sorted(top['components'])}"
)
scores = [item["match_score"] for item in items]
assert scores == sorted(scores, reverse=True), f"results are not sorted by score: {scores}"
reason = top["reasons"][0]
print(f"  top match {score:.2f}: {reason}")
' "/recommendations"

# MMR may diversify order away from pure score ranking — still must return valid rows.
curl -fsS "${BASE_URL}/recommendations?limit=5&mmr=true" -H "$AUTH" | assert_json '
items = body["items"]
assert items, "MMR recommendations returned nothing"
assert all(0.0 <= item["match_score"] <= 1.0 for item in items)
assert all(item["reasons"] for item in items)
print(f"  MMR returned {len(items)} explained matches")
' "/recommendations?mmr=true"

TOP_ID=$(printf '%s' "$recs" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["teacher"]["user_id"])')

step "Per-teacher explanation"
curl -fsS "${BASE_URL}/recommendations/${TOP_ID}/explain" -H "$AUTH" | assert_json '
factors = {row["factor"] for row in body["explanation"]}
assert "semantic" in factors, f"no semantic factor in {factors}"
listed = ", ".join(sorted(factors))
print(f"  factors: {listed}")
' "/recommendations/{id}/explain"

# --------------------------------------------------------------------------- #
step "Search returns results and reports its engine"
curl -fsS "${BASE_URL}/search/engine" | assert_json '
print(f"  engine: {body}")
' "/search/engine"

curl -fsS --get "${BASE_URL}/search/teachers" \
    --data-urlencode "query=students build real software in teams" \
    --data-urlencode "limit=5" | assert_json '
items = body["items"]
assert items, "semantic teacher search returned nothing"
print(f"  {len(items)} teachers matched")
' "/search/teachers"

curl -fsS "${BASE_URL}/resources?limit=5" | assert_json '
items = body["items"]
assert items, "no resources returned"
print(f"  {len(items)} resources listed")
' "/resources"

# --------------------------------------------------------------------------- #
# The full write path: a brand new account gets an embedding on profile create
# and is immediately matchable. Cleans up after itself.
step "Register -> profile -> recommendations -> delete"
NEW_EMAIL="smoke-$(date +%s)-$$@example.com"
new_body=$(curl -fsS -X POST "${BASE_URL}/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${NEW_EMAIL}\",\"password\":\"SmokeTest123!\",\"first_name\":\"Smoke\",\"last_name\":\"Test\"}")
NEW_TOKEN=$(printf '%s' "$new_body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
NEW_AUTH="Authorization: Bearer ${NEW_TOKEN}"

curl -fsS -X POST "${BASE_URL}/profiles" -H "$NEW_AUTH" -H 'Content-Type: application/json' -d '{
    "bio": "I teach computer science using project-based learning.",
    "location_name": "Boston, Massachusetts",
    "latitude": 42.36,
    "longitude": -71.06,
    "education_levels": ["high_school"],
    "subjects": ["computer_science", "python"],
    "fields_of_expertise": ["software_engineering"],
    "teaching_levels": ["beginner", "intermediate"],
    "teaching_methods": ["project_based", "collaborative"],
    "teaching_style": "Project-based and collaborative: students ship real software in teams.",
    "class_size": 25,
    "years_experience": 5,
    "languages": ["English"]
}' | assert_json '
assert body["user_id"], "the new profile has no user_id"
' "POST /profiles"

curl -fsS "${BASE_URL}/recommendations?limit=3" -H "$NEW_AUTH" | assert_json '
items = body["items"]
assert items, "a freshly created profile got no recommendations"
score = items[0]["match_score"]
print(f"  new teacher top match: {score:.2f}")
' "recommendations for a new account"

curl -fsS -X DELETE "${BASE_URL}/users/me" -H "$NEW_AUTH" -o /dev/null
printf '  cleaned up %s\n' "$NEW_EMAIL"

printf '\n\033[32mAll smoke checks passed against %s\033[0m\n' "$BASE_URL"
