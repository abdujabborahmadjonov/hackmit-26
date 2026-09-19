"""Vocabulary, city/school catalogs and prose templates for demo data.

Kept separate from the generator so the bulk-load logic stays readable while
the synthetic corpus can stay rich and opinionated.
"""

from __future__ import annotations

# (display name, lat, lon, languages spoken in classrooms)
CITIES: list[tuple[str, float, float, list[str]]] = [
    ("Boston, Massachusetts", 42.36, -71.06, ["English"]),
    ("Cambridge, Massachusetts", 42.37, -71.11, ["English"]),
    ("Somerville, Massachusetts", 42.39, -71.10, ["English", "Spanish"]),
    ("New York, New York", 40.71, -74.01, ["English", "Spanish"]),
    ("Brooklyn, New York", 40.68, -73.94, ["English", "Spanish"]),
    ("Philadelphia, Pennsylvania", 39.95, -75.17, ["English", "Spanish"]),
    ("Washington, District of Columbia", 38.91, -77.04, ["English", "Spanish"]),
    ("Atlanta, Georgia", 33.75, -84.39, ["English", "Spanish"]),
    ("Miami, Florida", 25.76, -80.19, ["English", "Spanish"]),
    ("Chicago, Illinois", 41.88, -87.63, ["English", "Spanish", "Polish"]),
    ("Detroit, Michigan", 42.33, -83.05, ["English", "Spanish", "Arabic"]),
    ("Minneapolis, Minnesota", 44.98, -93.27, ["English", "Somali", "Spanish"]),
    ("Austin, Texas", 30.27, -97.74, ["English", "Spanish"]),
    ("Houston, Texas", 29.76, -95.37, ["English", "Spanish"]),
    ("Denver, Colorado", 39.74, -104.99, ["English", "Spanish"]),
    ("Phoenix, Arizona", 33.45, -112.07, ["English", "Spanish"]),
    ("Los Angeles, California", 34.05, -118.24, ["English", "Spanish", "Korean"]),
    ("San Francisco, California", 37.77, -122.42, ["English", "Mandarin", "Spanish"]),
    ("Oakland, California", 37.80, -122.27, ["English", "Spanish"]),
    ("Portland, Oregon", 45.52, -122.68, ["English", "Spanish"]),
    ("Seattle, Washington", 47.61, -122.33, ["English", "Spanish", "Mandarin"]),
    ("Toronto, Ontario", 43.65, -79.38, ["English", "French", "Mandarin"]),
    ("Montreal, Quebec", 45.50, -73.57, ["French", "English"]),
    ("Vancouver, British Columbia", 49.28, -123.12, ["English", "Mandarin", "Punjabi"]),
    ("Edmonton, Alberta", 53.55, -113.49, ["English", "French"]),
    ("Calgary, Alberta", 51.05, -114.07, ["English", "French", "Punjabi"]),
    ("London, United Kingdom", 51.51, -0.13, ["English"]),
    ("Manchester, United Kingdom", 53.48, -2.24, ["English", "Urdu"]),
    ("Edinburgh, United Kingdom", 55.95, -3.19, ["English"]),
    ("Dublin, Ireland", 53.35, -6.26, ["English", "Irish"]),
    ("Berlin, Germany", 52.52, 13.41, ["German", "English"]),
    ("Amsterdam, Netherlands", 52.37, 4.90, ["Dutch", "English"]),
    ("Paris, France", 48.86, 2.35, ["French", "English"]),
    ("Barcelona, Spain", 41.39, 2.17, ["Spanish", "Catalan", "English"]),
    ("Stockholm, Sweden", 59.33, 18.07, ["Swedish", "English"]),
    ("Dubai, United Arab Emirates", 25.20, 55.27, ["English", "Arabic"]),
    ("Singapore", 1.35, 103.82, ["English", "Mandarin", "Malay", "Tamil"]),
    ("Hong Kong", 22.32, 114.17, ["Cantonese", "English", "Mandarin"]),
    ("Tokyo, Japan", 35.68, 139.69, ["Japanese", "English"]),
    ("Seoul, South Korea", 37.57, 126.98, ["Korean", "English"]),
    ("Sydney, Australia", -33.87, 151.21, ["English", "Mandarin"]),
    ("Melbourne, Australia", -37.81, 144.96, ["English", "Mandarin", "Vietnamese"]),
    ("Auckland, New Zealand", -36.85, 174.76, ["English", "Maori"]),
    ("Cape Town, South Africa", -33.92, 18.42, ["English", "Afrikaans", "Xhosa"]),
    ("Nairobi, Kenya", -1.29, 36.82, ["English", "Swahili"]),
    ("Lagos, Nigeria", 6.52, 3.38, ["English", "Yoruba", "Nigerian Pidgin"]),
    ("Sao Paulo, Brazil", -23.55, -46.63, ["Portuguese", "English", "Spanish"]),
    ("Mexico City, Mexico", 19.43, -99.13, ["Spanish", "English"]),
    ("Buenos Aires, Argentina", -34.60, -58.38, ["Spanish", "English"]),
    ("Tashkent, Uzbekistan", 41.30, 69.24, ["Uzbek", "Russian", "English"]),
    ("Almaty, Kazakhstan", 43.24, 76.95, ["Kazakh", "Russian", "English"]),
    ("Mumbai, India", 19.08, 72.88, ["English", "Hindi", "Marathi"]),
    ("Bengaluru, India", 12.97, 77.59, ["English", "Kannada", "Hindi"]),
    ("Delhi, India", 28.61, 77.21, ["English", "Hindi"]),
]

# Real / recognizable institutions keyed by city display name. Falls back to
# templated names when a city has no entry for a given band.
INSTITUTIONS: dict[str, dict[str, list[str]]] = {
    "Boston, Massachusetts": {
        "k12": [
            "Boston Latin School",
            "Boston Latin Academy",
            "Fenway High School",
            "Snowden International School",
            "Orchard Gardens K-8 Pilot School",
            "Josiah Quincy Elementary School",
        ],
        "higher": ["Northeastern University", "Boston University", "UMass Boston", "Suffolk University"],
        "adult": ["Bunker Hill Community College", "Boston Adult Technical Academy"],
    },
    "Cambridge, Massachusetts": {
        "k12": [
            "Cambridge Rindge and Latin School",
            "Amigos School",
            "Cambridge Street Upper School",
            "Graham and Parks School",
        ],
        "higher": ["Harvard University", "MIT", "Lesley University"],
        "adult": ["Cambridge Community Learning Center"],
    },
    "Somerville, Massachusetts": {
        "k12": ["Somerville High School", "Healey School", "Winter Hill Community Innovation School"],
        "higher": ["Tufts University"],
        "adult": ["SCALE Adult Education"],
    },
    "New York, New York": {
        "k12": [
            "Stuyvesant High School",
            "Bronx High School of Science",
            "Brooklyn Technical High School",
            "LaGuardia High School",
            "Beacon High School",
            "P.S. 234 Independence School",
        ],
        "higher": ["Columbia University", "NYU", "City College of New York", "Hunter College"],
        "adult": ["Borough of Manhattan Community College", "The New School Continuing Education"],
    },
    "Brooklyn, New York": {
        "k12": ["Brooklyn Technical High School", "Midwood High School", "P.S. 261"],
        "higher": ["Brooklyn College", "Pratt Institute"],
        "adult": ["Kingsborough Community College"],
    },
    "Philadelphia, Pennsylvania": {
        "k12": ["Central High School", "Science Leadership Academy", "Masterman School"],
        "higher": ["University of Pennsylvania", "Temple University", "Drexel University"],
        "adult": ["Community College of Philadelphia"],
    },
    "Washington, District of Columbia": {
        "k12": ["School Without Walls", "Duke Ellington School of the Arts", "Dunbar High School"],
        "higher": ["Georgetown University", "American University", "Howard University"],
        "adult": ["University of the District of Columbia Community College"],
    },
    "Atlanta, Georgia": {
        "k12": ["Grady High School", "North Atlanta High School", "Maynard Jackson High School"],
        "higher": ["Georgia Tech", "Emory University", "Georgia State University"],
        "adult": ["Atlanta Technical College"],
    },
    "Miami, Florida": {
        "k12": ["Design and Architecture Senior High", "Coral Gables Senior High", "MAST Academy"],
        "higher": ["University of Miami", "Florida International University"],
        "adult": ["Miami Dade College"],
    },
    "Chicago, Illinois": {
        "k12": [
            "Whitney Young Magnet High School",
            "Lane Tech College Prep",
            "Walter Payton College Prep",
            "Lincoln Park High School",
        ],
        "higher": ["University of Chicago", "Northwestern University", "UIC", "DePaul University"],
        "adult": ["City Colleges of Chicago"],
    },
    "Detroit, Michigan": {
        "k12": ["Cass Technical High School", "Renaissance High School", "Detroit School of Arts"],
        "higher": ["Wayne State University", "University of Detroit Mercy"],
        "adult": ["Wayne County Community College District"],
    },
    "Minneapolis, Minnesota": {
        "k12": ["Southwest High School", "South High School", "Washburn High School"],
        "higher": ["University of Minnesota", "Augsburg University"],
        "adult": ["Minneapolis College"],
    },
    "Austin, Texas": {
        "k12": ["Liberal Arts and Science Academy", "Anderson High School", "Austin High School"],
        "higher": ["University of Texas at Austin", "St. Edward's University"],
        "adult": ["Austin Community College"],
    },
    "Houston, Texas": {
        "k12": ["DeBakey High School for Health Professions", "Carnegie Vanguard", "Bellaire High School"],
        "higher": ["Rice University", "University of Houston", "Texas Southern University"],
        "adult": ["Houston Community College"],
    },
    "Denver, Colorado": {
        "k12": ["East High School", "Denver School of the Arts", "North High School"],
        "higher": ["University of Denver", "Metropolitan State University of Denver"],
        "adult": ["Community College of Denver"],
    },
    "Phoenix, Arizona": {
        "k12": ["Central High School", "Phoenix Union Bioscience High School", "Metro Tech High School"],
        "higher": ["Arizona State University", "University of Arizona Phoenix"],
        "adult": ["Phoenix College"],
    },
    "Los Angeles, California": {
        "k12": [
            "Los Angeles High School of the Arts",
            "Downtown Magnets High School",
            "Francisco Bravo Medical Magnet",
            "Venice High School",
        ],
        "higher": ["UCLA", "USC", "Cal State LA", "Loyola Marymount University"],
        "adult": ["Los Angeles City College", "East Los Angeles College"],
    },
    "San Francisco, California": {
        "k12": ["Lowell High School", "Ruth Asawa School of the Arts", "Galileo Academy"],
        "higher": ["San Francisco State University", "University of San Francisco", "UC Berkeley"],
        "adult": ["City College of San Francisco"],
    },
    "Oakland, California": {
        "k12": ["Oakland Technical High School", "Skyline High School", "MetWest High School"],
        "higher": ["Mills College at Northeastern", "California College of the Arts"],
        "adult": ["Laney College"],
    },
    "Portland, Oregon": {
        "k12": ["Lincoln High School", "Grant High School", "Jefferson High School"],
        "higher": ["Portland State University", "Reed College", "Lewis & Clark College"],
        "adult": ["Portland Community College"],
    },
    "Seattle, Washington": {
        "k12": ["Garfield High School", "Roosevelt High School", "Ballard High School", "Chief Sealth"],
        "higher": ["University of Washington", "Seattle University", "Seattle Pacific University"],
        "adult": ["Seattle Central College"],
    },
    "Toronto, Ontario": {
        "k12": [
            "University of Toronto Schools",
            "Northern Secondary School",
            "Marc Garneau Collegiate Institute",
            "Harbord Collegiate Institute",
        ],
        "higher": ["University of Toronto", "York University", "Toronto Metropolitan University"],
        "adult": ["George Brown College", "Seneca College"],
    },
    "Montreal, Quebec": {
        "k12": ["College Jean-de-Brebeuf", "FACE School", "Royal West Academy"],
        "higher": ["McGill University", "Universite de Montreal", "Concordia University"],
        "adult": ["Dawson College", "Vanier College"],
    },
    "Vancouver, British Columbia": {
        "k12": ["Lord Byng Secondary", "Kitsilano Secondary", "Prince of Wales Secondary"],
        "higher": ["University of British Columbia", "Simon Fraser University"],
        "adult": ["Vancouver Community College"],
    },
    "Edmonton, Alberta": {
        "k12": ["Old Scona Academic", "Victoria School of the Arts", "Strathcona High School"],
        "higher": ["University of Alberta", "MacEwan University"],
        "adult": ["NorQuest College"],
    },
    "Calgary, Alberta": {
        "k12": ["Western Canada High School", "Central Memorial High School", "Queen Elizabeth High"],
        "higher": ["University of Calgary", "Mount Royal University"],
        "adult": ["Bow Valley College"],
    },
    "London, United Kingdom": {
        "k12": [
            "Holland Park School",
            "The Latymer School",
            "St Marylebone School",
            "Mossbourne Community Academy",
        ],
        "higher": ["UCL", "King's College London", "Imperial College London", "LSE"],
        "adult": ["City Lit", "Morley College"],
    },
    "Manchester, United Kingdom": {
        "k12": ["Manchester Grammar School", "Withington Girls' School", "Trinity Church of England High"],
        "higher": ["University of Manchester", "Manchester Metropolitan University"],
        "adult": ["The Manchester College"],
    },
    "Edinburgh, United Kingdom": {
        "k12": ["Boroughmuir High School", "James Gillespie's High School", "George Heriot's School"],
        "higher": ["University of Edinburgh", "Heriot-Watt University"],
        "adult": ["Edinburgh College"],
    },
    "Dublin, Ireland": {
        "k12": ["Belvedere College", "Gonzaga College", "St. Kevin's College"],
        "higher": ["Trinity College Dublin", "University College Dublin", "Dublin City University"],
        "adult": ["City of Dublin ETB Adult Education"],
    },
    "Berlin, Germany": {
        "k12": ["John-F.-Kennedy-Schule", "Gymnasium Steglitz", "Heinrich-Schliemann-Gymnasium"],
        "higher": ["Humboldt-Universitat zu Berlin", "Freie Universitat Berlin", "TU Berlin"],
        "adult": ["Volkshochschule Berlin Mitte"],
    },
    "Amsterdam, Netherlands": {
        "k12": ["Amsterdams Lyceum", "Barlaeus Gymnasium", "Cartesius Lyceum"],
        "higher": ["University of Amsterdam", "Vrije Universiteit Amsterdam"],
        "adult": ["ROC van Amsterdam"],
    },
    "Paris, France": {
        "k12": ["Lycee Louis-le-Grand", "Lycee Henri-IV", "Lycee Condorcet"],
        "higher": ["Sorbonne Universite", "Sciences Po", "Universite Paris Cite"],
        "adult": ["Greta de Paris"],
    },
    "Barcelona, Spain": {
        "k12": ["Institut Vila de Gracia", "Escola Pia de Sarria", "Institut Menendez y Pelayo"],
        "higher": ["Universitat de Barcelona", "Universitat Pompeu Fabra", "UPC"],
        "adult": ["Escola Oficial d'Idiomes Barcelona"],
    },
    "Stockholm, Sweden": {
        "k12": ["Norra Real", "Kungsholmens Gymnasium", "Sodra Latin"],
        "higher": ["Stockholm University", "KTH Royal Institute of Technology"],
        "adult": ["Folkuniversitetet Stockholm"],
    },
    "Dubai, United Arab Emirates": {
        "k12": ["Dubai International Academy", "Jumeirah College", "GEMS World Academy"],
        "higher": ["American University in Dubai", "University of Dubai", "Heriot-Watt Dubai"],
        "adult": ["Dubai Knowledge Park Training Institutes"],
    },
    "Singapore": {
        "k12": [
            "Raffles Institution",
            "Hwa Chong Institution",
            "National Junior College",
            "School of Science and Technology",
        ],
        "higher": ["National University of Singapore", "Nanyang Technological University", "SMU"],
        "adult": ["Institute of Technical Education", "Singapore Polytechnic"],
    },
    "Hong Kong": {
        "k12": ["King's College", "Diocesan Boys' School", "St. Paul's Co-educational College"],
        "higher": ["University of Hong Kong", "Chinese University of Hong Kong", "HKUST"],
        "adult": ["Hong Kong Metropolitan University"],
    },
    "Tokyo, Japan": {
        "k12": ["Tokyo Metropolitan High School of Science and Technology", "Azabu High School"],
        "higher": ["University of Tokyo", "Waseda University", "Keio University"],
        "adult": ["Tokyo Metropolitan Adult Learning Centers"],
    },
    "Seoul, South Korea": {
        "k12": ["Seoul Science High School", "Hansung Science High School", "Daeil Foreign Language High"],
        "higher": ["Seoul National University", "Korea University", "Yonsei University"],
        "adult": ["Seoul Metropolitan Lifelong Learning Centers"],
    },
    "Sydney, Australia": {
        "k12": ["Sydney Boys High School", "Fort Street High School", "Newtown High School of the Performing Arts"],
        "higher": ["University of Sydney", "UNSW Sydney", "UTS"],
        "adult": ["TAFE NSW Ultimo"],
    },
    "Melbourne, Australia": {
        "k12": ["Melbourne High School", "Mac.Robertson Girls' High School", "University High School"],
        "higher": ["University of Melbourne", "Monash University", "RMIT University"],
        "adult": ["Holmesglen TAFE"],
    },
    "Auckland, New Zealand": {
        "k12": ["Auckland Grammar School", "Western Springs College", "Mount Albert Grammar School"],
        "higher": ["University of Auckland", "AUT"],
        "adult": ["Unitec Institute of Technology"],
    },
    "Cape Town, South Africa": {
        "k12": ["South African College High School", "Westerford High School", "Rustenburg Girls' High"],
        "higher": ["University of Cape Town", "Stellenbosch University"],
        "adult": ["False Bay TVET College"],
    },
    "Nairobi, Kenya": {
        "k12": ["Alliance High School", "Kenya High School", "Starehe Boys' Centre"],
        "higher": ["University of Nairobi", "Strathmore University", "Kenyatta University"],
        "adult": ["Kenya Technical Trainers College"],
    },
    "Lagos, Nigeria": {
        "k12": ["King's College Lagos", "Queen's College Lagos", "Atlantic Hall"],
        "higher": ["University of Lagos", "Pan-Atlantic University", "Lagos State University"],
        "adult": ["Yaba College of Technology"],
    },
    "Sao Paulo, Brazil": {
        "k12": ["Colegio Bandeirantes", "Colegio Santa Cruz", "Escola Estadual de Sao Paulo"],
        "higher": ["Universidade de Sao Paulo", "UNICAMP", "FGV"],
        "adult": ["SENAC Sao Paulo"],
    },
    "Mexico City, Mexico": {
        "k12": ["Preparatoria 6 Antonio Caso", "Colegio Madrid", "Instituto Escuela"],
        "higher": ["UNAM", "ITAM", "Universidad Iberoamericana"],
        "adult": ["Instituto Nacional para la Educacion de los Adultos"],
    },
    "Buenos Aires, Argentina": {
        "k12": ["Colegio Nacional de Buenos Aires", "Escuela Superior de Comercio Carlos Pellegrini"],
        "higher": ["Universidad de Buenos Aires", "UTN", "Universidad Torcuato Di Tella"],
        "adult": ["Centro de Formacion Profesional N 1"],
    },
    "Tashkent, Uzbekistan": {
        "k12": ["Presidential School in Tashkent", "Specialized School No. 60", "Mirzo Ulugbek School"],
        "higher": ["National University of Uzbekistan", "Tashkent University of Information Technologies"],
        "adult": ["Tashkent Professional College of Information Technologies"],
    },
    "Almaty, Kazakhstan": {
        "k12": ["Republican Physics and Mathematics School", "Haileybury Almaty", "NIS Almaty"],
        "higher": ["Al-Farabi Kazakh National University", "KIMEP University"],
        "adult": ["Almaty Management University Continuing Education"],
    },
    "Mumbai, India": {
        "k12": ["Cathedral and John Connon School", "Bombay Scottish School", "Jamnabai Narsee School"],
        "higher": ["IIT Bombay", "University of Mumbai", "Tata Institute of Social Sciences"],
        "adult": ["NMIMS School of Continuing Education"],
    },
    "Bengaluru, India": {
        "k12": ["National Public School Indiranagar", "Bishop Cotton Boys' School", "Mallya Aditi"],
        "higher": ["IISc Bangalore", "IIT Bangalore", "Christ University"],
        "adult": ["NIIT Bengaluru"],
    },
    "Delhi, India": {
        "k12": ["Delhi Public School R.K. Puram", "Modern School Barakhamba", "Sanskriti School"],
        "higher": ["University of Delhi", "Jawaharlal Nehru University", "IIT Delhi"],
        "adult": ["IGNOU Regional Centre Delhi"],
    },
}

# Finer buckets used by the generator. Raw INSTITUTIONS stay as k12/higher/adult
# for readability; this index splits them so elementary teachers never draw a
# high-school-only name and community_college never draws MIT.
_INSTITUTION_BUCKETS = (
    "elementary",
    "middle_school",
    "high_school",
    "university",
    "community_college",
    "adult",
)

_ELEMENTARY_HINTS = (
    "elementary",
    "primary",
    "k-5",
    "k-6",
    "grammar school",
    "p.s.",
    "ps ",
    "josiah quincy",
    "orchard gardens",
    "amigos school",
    "graham and parks",
    "healey school",
    "winter hill",
)

_MIDDLE_HINTS = (
    "middle school",
    "middle ",
    "junior high",
    "upper school",
    "k-8",
    "k-9",
    "intermediate school",
    "cambridge street upper",
)

_HIGH_HINTS = (
    "high school",
    "secondary",
    "senior high",
    "collegiate",
    "preparatory",
    "prep ",
    "academy",
    "lycee",
    "lycée",
    "gymnasium",
    "grammar",
    "sixth form",
    "preparatoria",
    "colegio",
    "college prep",
    "magnet",
    "technical high",
    "boys' school",
    "girls' school",
    "boys school",
    "girls school",
    "institution",  # Raffles Institution, Hwa Chong, etc.
    "junior college",
)

_COMMUNITY_COLLEGE_HINTS = (
    "community college",
    "community learning",
    "community college",
    "city college",
    "city colleges",
    "borough of",
    "tafe",
    "polytechnic",
    "continuing education",
    "adult education",
    "adult learning",
    "adult technical",
    "skills hub",
    "skills ",
    "technical college",
    "technical trainers",
    "tvet",
    "roc ",
    "greta",
    "volkshochschule",
    "senac",
    "niit",
    "ignou",
    "etb",
    "scale adult",
    "knowledge park",
    "lifelong learning",
    "formation professionnel",
    "norquest",
    "bow valley",
    "george brown",
    "seneca college",
    "dawson college",
    "vanier college",
    "bunker hill",
    "laney college",
    "phoenix college",
    "holmesglen",
    "unitec",
    "false bay",
    "yaba college",
    "morley college",
    "city lit",
    "manchester college",
    "edinburgh college",
    "vancouver community",
    "minneapolis college",
    "austin community",
    "houston community",
    "community college of",
    "city of dublin",
)


def _is_community_college_name(name: str) -> bool:
    low = name.lower()
    if "university" in low and "community" not in low:
        return False
    return any(hint in low for hint in _COMMUNITY_COLLEGE_HINTS)


def _classify_k12(name: str) -> list[str]:
    """Return one or more k12 buckets this name is compatible with."""
    low = name.lower()
    buckets: list[str] = []
    if any(hint in low for hint in _ELEMENTARY_HINTS):
        buckets.append("elementary")
    if any(hint in low for hint in _MIDDLE_HINTS):
        buckets.append("middle_school")
    if any(hint in low for hint in _HIGH_HINTS):
        buckets.append("high_school")
    # K-8 / all-through schools serve elementary + middle.
    if "k-8" in low or "k-9" in low:
        for band in ("elementary", "middle_school"):
            if band not in buckets:
                buckets.append(band)
    return buckets


def _build_institution_lookup(
    raw: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    lookup: dict[str, dict[str, list[str]]] = {}
    for city, bands in raw.items():
        buckets: dict[str, list[str]] = {key: [] for key in _INSTITUTION_BUCKETS}
        for name in bands.get("k12", []):
            classified = _classify_k12(name)
            if classified:
                for band in classified:
                    buckets[band].append(name)
            else:
                # Unclassified recognisable schools default to high school only —
                # never silently handed to elementary profiles.
                buckets["high_school"].append(name)
        for name in bands.get("higher", []):
            if _is_community_college_name(name):
                buckets["community_college"].append(name)
            else:
                buckets["university"].append(name)
        for name in bands.get("adult", []):
            buckets["adult"].append(name)
            if _is_community_college_name(name):
                buckets["community_college"].append(name)
        lookup[city] = buckets
    return lookup


INSTITUTION_LOOKUP: dict[str, dict[str, list[str]]] = _build_institution_lookup(INSTITUTIONS)

# Subjects / expertise / class sizes that make sense at each education level.
LEVEL_PROFILES: dict[str, dict] = {
    "elementary": {
        "subjects": [
            "mathematics",
            "english",
            "art",
            "music",
            "biology",
            "history",
            "physical_education",
        ],
        "expertise": [
            "literacy",
            "numeracy",
            "classroom_management",
            "social_emotional_learning",
            "phonics",
            "inclusion",
            "play_based_learning",
            "early_childhood",
        ],
        "class_size": (16, 28),
        "levels": ["beginner"],
        "institution_types": ["public_school", "private_school", "charter_school"],
        "method_weights": {
            "hands_on": 22,
            "game_based": 18,
            "collaborative": 16,
            "project_based": 14,
            "inquiry_based": 12,
            "discussion_based": 8,
            "flipped_classroom": 4,
            "problem_based": 4,
            "socratic": 1,
            "lecture_based": 1,
        },
    },
    "middle_school": {
        "subjects": [
            "mathematics",
            "english",
            "history",
            "biology",
            "computer_science",
            "art",
            "music",
            "chemistry",
            "physical_education",
        ],
        "expertise": [
            "project_design",
            "differentiation",
            "stem_outreach",
            "literacy",
            "classroom_management",
            "advisory",
            "makerspace",
            "adolescent_development",
        ],
        "class_size": (18, 32),
        "levels": ["beginner", "intermediate"],
        "institution_types": ["public_school", "charter_school", "private_school"],
        "method_weights": {
            "project_based": 20,
            "collaborative": 18,
            "hands_on": 14,
            "inquiry_based": 12,
            "game_based": 10,
            "discussion_based": 10,
            "problem_based": 8,
            "flipped_classroom": 5,
            "socratic": 2,
            "lecture_based": 1,
        },
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
            "art",
            "music",
            "psychology",
            "business",
        ],
        "expertise": [
            "software_engineering",
            "robotics",
            "lab_design",
            "exam_preparation",
            "curriculum_design",
            "python",
            "ap_ib_programmes",
            "college_counseling",
            "debate",
            "maker_education",
            "web_development",
            "data_science",
        ],
        "class_size": (16, 34),
        "levels": ["beginner", "intermediate", "advanced"],
        "institution_types": ["public_school", "private_school", "charter_school"],
        "method_weights": {
            "project_based": 18,
            "problem_based": 14,
            "collaborative": 14,
            "inquiry_based": 12,
            "flipped_classroom": 10,
            "hands_on": 10,
            "discussion_based": 8,
            "socratic": 6,
            "lecture_based": 5,
            "game_based": 3,
        },
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
            "chemistry",
            "biology",
            "history",
            "english",
        ],
        "expertise": [
            "machine_learning",
            "data_science",
            "research_methods",
            "software_engineering",
            "academic_writing",
            "undergraduate_research",
            "assessment_design",
            "open_educational_resources",
            "industry_partnerships",
            "python",
            "web_development",
        ],
        "class_size": (25, 180),
        "levels": ["intermediate", "advanced"],
        "institution_types": ["university", "community_college"],
        "method_weights": {
            "lecture_based": 18,
            "discussion_based": 16,
            "project_based": 14,
            "problem_based": 12,
            "flipped_classroom": 12,
            "socratic": 10,
            "collaborative": 8,
            "inquiry_based": 6,
            "hands_on": 3,
            "game_based": 1,
        },
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
            "computer_science",
            "mathematics",
            "biology",
            "chemistry",
        ],
        "expertise": [
            "research_methods",
            "quantum_computing",
            "deep_learning",
            "thesis_supervision",
            "grant_writing",
            "academic_writing",
            "seminar_facilitation",
            "peer_review",
            "data_science",
        ],
        "class_size": (6, 28),
        "levels": ["advanced"],
        "institution_types": ["university"],
        "method_weights": {
            "socratic": 20,
            "discussion_based": 20,
            "inquiry_based": 16,
            "lecture_based": 14,
            "problem_based": 12,
            "project_based": 10,
            "collaborative": 6,
            "flipped_classroom": 2,
            "hands_on": 0,
            "game_based": 0,
        },
    },
    "adult_education": {
        "subjects": [
            "english",
            "business",
            "computer_science",
            "mathematics",
            "art",
            "statistics",
            "economics",
        ],
        "expertise": [
            "career_transition",
            "esl",
            "workplace_training",
            "programming",
            "financial_literacy",
            "digital_literacy",
            "job_readiness",
            "andragogy",
        ],
        "class_size": (8, 24),
        "levels": ["beginner", "intermediate"],
        "institution_types": ["community_college", "online_academy", "nonprofit", "independent"],
        "method_weights": {
            "hands_on": 18,
            "project_based": 16,
            "collaborative": 14,
            "flipped_classroom": 12,
            "problem_based": 12,
            "discussion_based": 10,
            "lecture_based": 8,
            "inquiry_based": 5,
            "game_based": 3,
            "socratic": 2,
        },
    },
}

# When a teacher has subject X, prefer expertise from this map.
SUBJECT_EXPERTISE: dict[str, list[str]] = {
    "mathematics": ["numeracy", "exam_preparation", "curriculum_design", "data_science", "statistics"],
    "physics": ["lab_design", "robotics", "curriculum_design", "exam_preparation"],
    "chemistry": ["lab_design", "curriculum_design", "exam_preparation"],
    "biology": ["lab_design", "curriculum_design", "exam_preparation", "inclusion"],
    "computer_science": [
        "software_engineering",
        "python",
        "web_development",
        "robotics",
        "programming",
        "data_science",
    ],
    "artificial_intelligence": ["machine_learning", "data_science", "python", "research_methods"],
    "machine_learning": ["deep_learning", "data_science", "python", "research_methods", "statistics"],
    "english": ["literacy", "academic_writing", "debate", "esl", "phonics"],
    "history": ["curriculum_design", "debate", "project_design", "primary_sources"],
    "economics": ["data_science", "exam_preparation", "financial_literacy", "curriculum_design"],
    "business": ["workplace_training", "financial_literacy", "industry_partnerships", "career_transition"],
    "art": ["portfolio_development", "inclusion", "project_design", "makerspace"],
    "music": ["ensemble_direction", "curriculum_design", "inclusion"],
    "engineering": ["robotics", "maker_education", "lab_design", "prototyping"],
    "psychology": ["research_methods", "adolescent_development", "social_emotional_learning"],
    "statistics": ["data_science", "research_methods", "exam_preparation", "numeracy"],
    "physical_education": ["inclusion", "classroom_management", "adolescent_development"],
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
    "{topic} — a {level} {kind}",
    "{kind} for teaching {topic}",
    "{subject} unit: {topic}",
    "Ready-to-run {kind}: {topic}",
    "{topic} workshop pack ({level})",
    "From zero to {topic}: {kind}",
    "{subject} studio day — {topic}",
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
    "syllabus": "syllabus",
    "homework": "homework set",
}

TOPICS: dict[str, list[str]] = {
    "mathematics": [
        "fractions",
        "quadratics",
        "vectors",
        "probability",
        "geometry proofs",
        "linear systems",
        "exponentials",
        "number sense",
        "trigonometric identities",
        "absolute value inequalities",
    ],
    "physics": [
        "kinematics",
        "circuits",
        "waves",
        "thermodynamics",
        "optics",
        "momentum",
        "electric fields",
        "simple harmonic motion",
    ],
    "chemistry": [
        "stoichiometry",
        "acids and bases",
        "periodic trends",
        "reaction rates",
        "bonding models",
        "electrochemistry",
        "organic functional groups",
    ],
    "biology": [
        "cell division",
        "genetics",
        "ecosystems",
        "photosynthesis",
        "homeostasis",
        "evolution evidence",
        "human physiology",
    ],
    "computer_science": [
        "functions",
        "recursion",
        "data structures",
        "web apps",
        "debugging",
        "APIs",
        "version control",
        "algorithms",
        "cybersecurity basics",
    ],
    "english": [
        "persuasive writing",
        "close reading",
        "poetry analysis",
        "narrative craft",
        "research essays",
        "media literacy",
        "literary devices",
    ],
    "history": [
        "primary sources",
        "industrial revolution",
        "civil rights",
        "world war one",
        "decolonisation",
        "local history projects",
        "historiography",
    ],
    "economics": [
        "supply and demand",
        "elasticity",
        "market failure",
        "game theory",
        "inflation",
        "trade-offs",
        "behavioral economics",
    ],
    "business": [
        "business models",
        "pitching",
        "market research",
        "financial literacy",
        "customer interviews",
        "operations basics",
    ],
    "art": [
        "colour theory",
        "portfolio building",
        "printmaking",
        "digital illustration",
        "observational drawing",
        "critique protocols",
    ],
    "music": [
        "rhythm training",
        "ensemble skills",
        "music theory",
        "composition",
        "ear training",
        "rehearsal routines",
    ],
    "engineering": [
        "CAD basics",
        "bridge design",
        "materials testing",
        "prototyping",
        "design constraints",
        "failure analysis",
    ],
    "psychology": [
        "research ethics",
        "memory",
        "developmental stages",
        "bias",
        "experimental design",
        "social influence",
    ],
    "statistics": [
        "hypothesis testing",
        "regression",
        "sampling",
        "data visualisation",
        "confidence intervals",
        "experimental vs observational",
    ],
    "artificial_intelligence": [
        "search algorithms",
        "ethics of AI",
        "prompting",
        "agents",
        "representation learning",
        "evaluation pitfalls",
    ],
    "machine_learning": [
        "train/test splits",
        "overfitting",
        "neural networks",
        "embeddings",
        "feature engineering",
        "model cards",
    ],
    "literacy": ["phonics", "reading fluency", "vocabulary building", "guided reading"],
    "numeracy": ["number sense", "mental maths", "place value", "estimation strategies"],
    "python": ["loops", "list comprehensions", "unit testing", "APIs", "pandas basics"],
    "robotics": ["line following", "sensor calibration", "gear ratios", "PID control"],
    "physical_education": ["skill progressions", "inclusive games", "fitness circuits", "team tactics"],
}

# City indices weighted so coastal / major hubs are denser (better proximity demos).
CITY_WEIGHTS: list[int] = [
    8,  # Boston
    7,  # Cambridge
    4,  # Somerville
    9,  # New York
    5,  # Brooklyn
    4,  # Philadelphia
    4,  # DC
    3,  # Atlanta
    3,  # Miami
    6,  # Chicago
    2,  # Detroit
    2,  # Minneapolis
    4,  # Austin
    3,  # Houston
    3,  # Denver
    3,  # Phoenix
    6,  # LA
    5,  # SF
    3,  # Oakland
    3,  # Portland
    5,  # Seattle
    5,  # Toronto
    3,  # Montreal
    3,  # Vancouver
    2,  # Edmonton
    2,  # Calgary
    6,  # London
    2,  # Manchester
    2,  # Edinburgh
    2,  # Dublin
    3,  # Berlin
    2,  # Amsterdam
    3,  # Paris
    2,  # Barcelona
    2,  # Stockholm
    3,  # Dubai
    4,  # Singapore
    2,  # Hong Kong
    3,  # Tokyo
    2,  # Seoul
    3,  # Sydney
    2,  # Melbourne
    1,  # Auckland
    2,  # Cape Town
    2,  # Nairobi
    2,  # Lagos
    3,  # Sao Paulo
    3,  # Mexico City
    2,  # Buenos Aires
    2,  # Tashkent
    1,  # Almaty
    3,  # Mumbai
    3,  # Bengaluru
    3,  # Delhi
]

assert len(CITY_WEIGHTS) == len(CITIES)

STYLE_TAILS = [
    "Assessment is mostly formative, with plenty of peer feedback.",
    "Every unit ends with something students can show to a real audience.",
    "I plan backwards from the skill I want students to walk out with.",
    "I care more about students explaining their thinking than final answers.",
    "Exit tickets and cold-call routines keep every voice in the room.",
    "I publish exemplars early so students know what 'good' looks like.",
    "We iterate publicly: drafts on the wall, critique protocols, revise again.",
    "Technology is a tool, not the point — I only adopt what reduces friction.",
    "I build transfer intentionally: same idea, three contexts, one week apart.",
    "Classroom norms are co-authored with students in the first fortnight.",
    "I keep a living question board; unfinished curiosity becomes next week's hook.",
    "Feedback is actionable and short — one glow, one grow, then time to act.",
]

BIO_HOOKS = [
    "I run an after-school club that draws students who rarely speak up in class.",
    "Department colleagues borrow my unit maps more than my slide decks.",
    "I mentor early-career teachers on classroom culture more than content.",
    "Parents know me as the person who answers emails with a next step, not jargon.",
    "I have rewritten our scope-and-sequence twice and still tweak it yearly.",
    "Outside class I coach debate / robotics / journalism depending on the year.",
    "I publish open resources because locked PDFs help nobody.",
    "I measure success by who comes back to visit after graduating.",
    "I collaborate across departments whenever a project can carry two standards.",
    "I keep a failure wall of experiments that almost worked — students love it.",
]

RATING_COMMENTS = [
    "Generous with materials and quick to answer questions.",
    "We co-planned a unit together — clear thinker, great with scaffolding.",
    "Their project briefs saved me a fortnight of planning.",
    "Ran a workshop for our department that actually changed how we teach.",
    "Helpful, but the resources needed some adapting for my class.",
    "Excellent at assessment design.",
    "Showed up to my classroom observation with concrete next steps, not vibes.",
    "Shared a full unit including student work samples — rare and valuable.",
    "Strong on inclusion; their differentiation notes were the useful part.",
    "Great collaborator across time zones; async comments were precise.",
    "Warm in person, rigorous on standards — hard combo to find.",
    "I disagreed with their pacing, but the discussion made my unit better.",
    "Sent me three alternatives when the first approach flopped with my cohort.",
    "Their rubric language is the clearest I've borrowed this year.",
    None,
    None,
]

MESSAGE_OPENERS = [
    "Hi! We seem to teach the same unit — fancy swapping materials?",
    "Your project brief looked great. How long do students spend on it?",
    "Would you be up for co-running a workshop next term?",
    "How do you handle assessment for group projects?",
    "Saw your resource on {topic} — mind if I adapt it for {level}?",
    "We're rewriting our {subject} pathway. Open to a 20-minute call?",
    "Any tips for cold-starting {topic} with mixed prior knowledge?",
    "I loved the critique protocol in your pack. Does it scale past 30 students?",
    "Looking for a peer to pressure-test a new {subject} performance task.",
    "Our PD day has a free slot — interested in a short demo of your approach?",
]

MESSAGE_REPLIES = [
    "Absolutely — I'll send over what I use this week.",
    "Happy to chat. Mine runs across three weeks including the demo day.",
    "Yes! Let me check with my department head and get back to you.",
    "Glad it landed. Happy to walk you through the tricky parts live.",
    "Sure — I can share the anonymised student samples too.",
    "I'm free Thursday after school if that works for you.",
    "Take whatever you need; just credit the original student-facing language.",
    "I'd love a second set of eyes on version two — sending a link.",
]
