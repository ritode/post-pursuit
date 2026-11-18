import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent / "profile.json"


def load_profile():
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "years_of_experience": 6,
        "min_score": 7.0,
        "primary_skills": ["react", "typescript", "javascript", "python", "django", "fastapi", "nextjs"],
        "secondary_skills": [],
        "ai_skills": [],
        "offtarget_tech": [],
        "exclude_seniority": ["intern", "werkstudent", "trainee", "praktikum"],
        "target_roles": ["frontend", "react", "full stack", "fullstack", "software engineer"]
    }


# --------------------------------------------------
# Result
# --------------------------------------------------

@dataclass
class FilterResult:
    status: str = "pending"         # passed | rejected | pending
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0              # 0.0 to 10.0 scale
    seniority: str = "unknown"
    work_model: str = "unknown"
    employment_type: str = "unknown"
    requires_german: str = "none detected"
    visa_mentioned: bool = False
    tech_stack: list[str] = field(default_factory=list)


# --------------------------------------------------
# Seniority Extraction
# --------------------------------------------------

SENIORITY_MAP = [
    (r"\bstaff\b", "staff"),
    (r"\bprincipal\b", "principal"),
    (r"\blead\b|\btech\s+lead\b", "lead"),
    (r"\bsenior\b|\bsr\.?\b", "senior"),
    (r"\bjunior\b|\bjr\.?\b", "junior"),
    (r"\bmid[\s-]?level\b", "mid"),
]


def detect_seniority(title, exclude_keywords):
    t = title.lower()

    for pattern in exclude_keywords:
        if re.search(rf"\b{re.escape(pattern)}\b", t) or pattern in t:
            return "intern"

    for pattern, level in SENIORITY_MAP:
        if re.search(pattern, t):
            return level

    return "mid"  # default assumption for unspecified roles


# --------------------------------------------------
# Work Model & Employment Type
# --------------------------------------------------

REMOTE_PATTERNS = [
    r"\bremote\b",
    r"\bhome[\s-]?office\b",
    r"\b100\s*%\s*remote\b",
    r"\bfully\s+remote\b",
    r"\bvollständig\s+remote\b",
]

HYBRID_PATTERNS = [
    r"\bhybrid\b",
    r"\btage\s+remote\b",
    r"\bdays?\s+remote\b",
    r"\bteilweise\s+remote\b",
]

ONSITE_PATTERNS = [
    r"\bon[\s-]?site\b",
    r"\bvor\s+ort\b",
    r"\bin[\s-]?office\b",
    r"\bpräsenz\b",
]


def detect_work_model(title, description):
    text = f"{title} {description or ''}".lower()

    for p in REMOTE_PATTERNS:
        if re.search(p, text):
            return "remote"

    for p in HYBRID_PATTERNS:
        if re.search(p, text):
            return "hybrid"

    for p in ONSITE_PATTERNS:
        if re.search(p, text):
            return "onsite"

    return "unknown"


def detect_employment_type(title, description):
    text = f"{title} {description or ''}".lower()

    if re.search(r"\bpart[\s-]?time\b|\bteilzeit\b", text):
        return "part-time"

    if re.search(r"\bcontract\b|\bfreelance\b|\bfreiberuf", text):
        return "contract"

    return "full-time"


# --------------------------------------------------
# Language & Visa Detection
# --------------------------------------------------

GERMAN_PATTERNS = [
    (r"\bgerman\b.*?\b(c[12]|b[12]|native|fluent|mutter)", None),
    (r"\bdeutsch\b.*?\b(c[12]|b[12]|fließend|mutter|verhandlungssicher)", None),
    (r"\b(c[12]|b[12])\b.*?\b(german|deutsch)\b", None),
    (r"\bfließend\w*\s+deutsch", "fluent"),
    (r"\bverhandlungssicher\w*\s+deutsch", "fluent"),
    (r"\bnative\s+german\b", "native"),
    (r"\bgerman\s+language\s+skills?\s+required", "required"),
]

GERMAN_LEVEL_EXTRACT = re.compile(r"\b([abc][12])\b", re.IGNORECASE)


def detect_language_requirements(description):
    if not description:
        return "none detected"

    text = description.lower()

    for pattern, label in GERMAN_PATTERNS:
        match = re.search(pattern, text)
        if match:
            if label:
                return label
            level = GERMAN_LEVEL_EXTRACT.search(match.group(0))
            if level:
                return level.group(1).upper()
            return "required"

    if (
        re.search(r"\b(?:german|deutsch)\s+(?:is\s+)?(?:required|mandatory|pflicht|erforderlich|vorausgesetzt)\b", text)
        or re.search(r"\b(?:must\s+speak|knowledge\s+of|proficiency\s+in|fluent\s+in)\s+(?:german|deutsch)\b", text)
        or re.search(r"\b(?:deutschkenntnisse|sprachkenntnisse\s+deutsch)\b", text)
        or re.search(r"\bgerman\s+(?:language\s+)?(?:skills?\s+)?(?:are\s+|is\s+)?required\b", text)
    ):
        return "required"

    return "none detected"


# Explicit rejection phrases when companies do NOT sponsor foreign internationals
NO_SPONSORSHIP_PATTERNS = [
    r"no\s+visa\s+sponsorship",
    r"without\s+(?:the\s+)?need\s+for\s+sponsorship",
    r"unable\s+to\s+sponsor",
    r"cannot\s+sponsor",
    r"will\s+not\s+sponsor",
    r"not\s+offering\s+sponsorship",
    r"not\s+providing\s+sponsorship",
    r"does\s+not\s+offer\s+visa",
    r"do\s+not\s+offer\s+visa",
    r"must\s+have\s+(?:valid\s+)?work\s+authorization",
    r"must\s+have\s+(?:a\s+)?valid\s+work\s+permit",
    r"must\s+be\s+authorized\s+to\s+work",
    r"must\s+already\s+have\s+(?:the\s+)?right\s+to\s+work",
    r"already\s+have\s+the\s+legal\s+right\s+to\s+work",
    r"eligible\s+to\s+work\s+in\s+.*?without\s+(?:any\s+)?(?:visa\s+)?sponsorship",
    r"right\s+to\s+work\s+in\s+.*?without\s+(?:any\s+)?(?:visa\s+)?sponsorship",
    r"valid\s+(?:eu|uk|german|australian|irish)\s+work\s+permit\s+required",
    r"gültige\s+arbeitserlaubnis\s+(?:erforderlich|vorausgesetzt)",
    r"keine\s+visasponsoring",
    r"keine\s+arbeitserlaubnis\s+gesponsert",
    r"only\s+candidates\s+with\s+(?:a\s+)?valid\s+work\s+permit",
    r"candidates\s+must\s+currently\s+reside\s+in",
    r"currently\s+living\s+in\s+(?:germany|the\s+netherlands|the\s+uk|australia|ireland)",
]

# Explicit positive patterns when companies welcome foreign talent / sponsor visas
SPONSORSHIP_PATTERNS = [
    r"visa\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)",
    r"offers?\s+visa\s+sponsorship",
    r"provide\s+visa\s+sponsorship",
    r"relocation\s+(?:support|package|assistance|allowance)",
    r"relocation\s+to\s+",
    r"help\s+(?:you\s+)?relocate",
    r"eu\s+blue\s+card",
    r"blue\s+card\s+eligible",
    r"global\s+mobility",
    r"open\s+to\s+international\s+applicants",
    r"we\s+sponsor\s+visas?",
    r"sponsorship\s+available",
    r"visum\s+sponsoring",
    r"unterstützung\s+beim\s+umzug",
]

VISA_PATTERNS = [
    r"\bvisa\b",
    r"\bsponsorship\b",
    r"\brelocation\b",
    r"\bwork\s+permit\b",
    r"\baufenthalts",
    r"\barbeitserlaubnis\b",
    r"\bumzug",
]


def detect_no_sponsorship(description):
    """Detect if the job posting explicitly refuses visa sponsorship or requires existing work permits."""
    if not description:
        return False
    text = description.lower()
    for p in NO_SPONSORSHIP_PATTERNS:
        if re.search(p, text):
            return True
    return False


def detect_visa_sponsorship(description):
    """Detect if the job posting explicitly offers visa sponsorship or relocation."""
    if not description:
        return False
    text = description.lower()
    for p in SPONSORSHIP_PATTERNS:
        if re.search(p, text):
            return True
    return False


def detect_visa_mentioned(description):
    if not description:
        return False
    text = description.lower()
    return any(bool(re.search(p, text)) for p in VISA_PATTERNS)


# --------------------------------------------------
# 0–10 Scoring Function
# --------------------------------------------------

def apply_filters(job, profile=None):
    """Run profile-based deterministic filtering and 0-10 scoring.

    Returns a FilterResult with status ('passed', 'rejected', 'pending'),
    reasons, and a composite score between 0.0 and 10.0.
    """
    if profile is None:
        profile = load_profile()

    title = (job.get("title") or "").strip()
    description = job.get("description")
    text = f"{title} {description or ''}".lower()

    result = FilterResult()

    # 1. Metadata extraction
    exclude_seniority = profile.get("exclude_seniority", [])
    result.seniority = detect_seniority(title, exclude_seniority)
    result.work_model = detect_work_model(title, description)
    result.employment_type = detect_employment_type(title, description)
    result.requires_german = detect_language_requirements(description)
    result.visa_mentioned = detect_visa_mentioned(description)

    # Hard rejection for intern/student roles
    if result.seniority == "intern":
        result.status = "rejected"
        result.reasons.append("seniority:intern_or_student")
        result.score = 0.0
        return result

    # Hard rejection if strict German C1/C2/fluent is required
    if result.requires_german in ("C1", "C2", "native", "fluent", "required"):
        result.status = "rejected"
        result.reasons.append(f"language:german_{result.requires_german.lower()}")
        result.score = 0.0
        return result

    # Hard rejection if posting explicitly refuses visa sponsorship or requires existing work permits
    if detect_no_sponsorship(description):
        result.status = "rejected"
        result.reasons.append("visa:no_sponsorship")
        result.score = 0.0
        return result

    # 2. Match Skills
    matched_skills = []

    primary_skills = profile.get("primary_skills", [])
    primary_matches = []
    for skill in primary_skills:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text):
            primary_matches.append(skill)
            matched_skills.append(skill)

    secondary_skills = profile.get("secondary_skills", [])
    secondary_matches = []
    for skill in secondary_skills:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text):
            secondary_matches.append(skill)
            matched_skills.append(skill)

    ai_skills = profile.get("ai_skills", [])
    ai_matches = []
    for skill in ai_skills:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text):
            ai_matches.append(skill)
            matched_skills.append(skill)

    # Off-target tech detection
    offtarget_tech = profile.get("offtarget_tech", [])
    offtarget_matches = []
    for skill in offtarget_tech:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text):
            offtarget_matches.append(skill)

    result.tech_stack = list(dict.fromkeys(matched_skills))

    # 3. Role Title Matching
    target_roles = profile.get("target_roles", [])
    role_matched = any(
        re.search(rf"\b{re.escape(role)}\b", title.lower())
        for role in target_roles
    )

    # 4. Handle Pending (no description)
    if not description:
        result.status = "pending"
        result.reasons.append("no_description")
        title_score = 0.0
        if role_matched:
            title_score += 3.5
        if any(skill in title.lower() for skill in ["react", "frontend", "fullstack", "typescript"]):
            title_score += 2.5
        result.score = round(min(6.0, title_score), 1)
        return result

    # Hard rejection: neither role nor any primary skill present
    if not role_matched and len(primary_matches) == 0:
        result.status = "rejected"
        result.reasons.append("tech:no_role_or_primary_match")
        result.score = 0.0
        return result

    # 5. Composite 0–10 Scoring
    score = 0.0

    # A. Role Match (up to 2.5 pts)
    if role_matched:
        score += 2.5
    else:
        score += 1.0

    # B. Primary Skills Match (up to 3.5 pts)
    # 1 skill: 1.5, 2 skills: 2.5, 3+ skills: 3.5
    if len(primary_matches) >= 3:
        score += 3.5
    elif len(primary_matches) == 2:
        score += 2.5
    elif len(primary_matches) == 1:
        score += 1.5

    # C. Secondary Skills Match (up to 2.0 pts)
    # Scale based on count (e.g. 5+ secondary skills = full 2.0 pts)
    sec_pts = min(2.0, len(secondary_matches) * 0.4)
    score += sec_pts

    # D. AI Skills Bonus (up to 0.5 pt)
    if len(ai_matches) > 0:
        score += 0.5

    # E. Seniority Fit for 6 Years of Experience (up to 1.5 pts)
    # User has 6 years -> Senior / Mid is ideal (1.5), Lead/Staff (1.0), Junior (0.3)
    if result.seniority in ("senior", "mid"):
        score += 1.5
    elif result.seniority in ("lead", "staff"):
        score += 1.0
    elif result.seniority == "junior":
        score += 0.3
    else:
        score += 1.0

    # F. Visa Sponsorship Bonus (+1.5 pts)
    has_sponsorship = detect_visa_sponsorship(description) or bool(job.get("visa_sponsored"))
    if has_sponsorship:
        result.visa_mentioned = True
        result.reasons.append("visa:sponsorship_offered")
        score += 1.5
    elif detect_visa_mentioned(description):
        result.visa_mentioned = True

    # G. Penalties for conflicting stacks (e.g. pure PHP/Laravel, COBOL, SAP)
    if offtarget_matches and len(primary_matches) <= 1:
        score -= min(2.0, len(offtarget_matches) * 0.6)

    # Clamp score to 0.0 - 10.0
    final_score = round(max(0.0, min(10.0, score)), 1)
    result.score = final_score

    min_score = profile.get("min_score", 7.0)
    if final_score >= min_score:
        result.status = "passed"
    else:
        result.status = "rejected"
        result.reasons.append(f"score_below_{min_score}")

    return result
