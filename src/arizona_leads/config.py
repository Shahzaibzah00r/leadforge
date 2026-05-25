"""Configuration constants for the Leads scraper — generic state/country support."""

import os
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

LEADS_CSV = OUTPUT_DIR / "leads.csv"
LEADS_JSON = OUTPUT_DIR / "leads.json"
LEADS_WITH_EMAIL_CSV = OUTPUT_DIR / "leads_with_email.csv"
LEADS_NO_EMAIL_CSV = OUTPUT_DIR / "leads_no_email.csv"
REPORT_MD = OUTPUT_DIR / "run_report.md"
REJECTED_CSV = OUTPUT_DIR / "rejected_candidates.csv"

# Throttling & limits
REQUEST_DELAY_MIN: float = 0.5
REQUEST_DELAY_MAX: float = 1.5
FETCH_TIMEOUT: int = 10
MAX_QUERIES: int = int(os.getenv("MAX_QUERIES", "100"))
MAX_CANDIDATES: int = int(os.getenv("MAX_CANDIDATES", "2000"))
MIN_RESULTS_PER_QUERY: int = 3
SEARCH_ENGINE_FAILURE_THRESHOLD: int = 10
REQUIRE_EMAIL: bool = os.getenv("REQUIRE_EMAIL", "").lower() in ("1", "true", "yes")

# Geography config (override via env or CLI)
STATE: str = os.getenv("SCRAPER_STATE", "Arizona")
STATE_ABBR: str = os.getenv("SCRAPER_STATE_ABBR", "AZ")
COUNTRY: str = os.getenv("SCRAPER_COUNTRY", "USA")

_CITIES_RAW = os.getenv("SCRAPER_CITIES", "")
if _CITIES_RAW:
    CITIES = [c.strip() for c in _CITIES_RAW.split(",") if c.strip()]
else:
    CITIES = [
        "Phoenix",
        "Scottsdale",
        "Mesa",
        "Tucson",
        "Tempe",
        "Chandler",
        "Glendale",
        "Gilbert",
        "Peoria",
        "Surprise",
        "Yuma",
        "Flagstaff",
        "Prescott",
        "Sedona",
        "Kingman",
        "Lake Havasu City",
        "Payson",
        "Show Low",
        "Cottonwood",
        "Sierra Vista",
        "Bullhead City",
        "Nogales",
        "Holbrook",
        "Winslow",
        "Globe",
        "Safford",
        "Thatcher",
        "Casa Grande",
        "Maricopa",
        "Oro Valley",
        "Goodyear",
        "Avondale",
        "Queen Creek",
        "San Tan Valley",
        "Buckeye",
        "Fountain Hills",
        "Paradise Valley",
        "Apache Junction",
        "El Mirage",
        "Sun City",
        "Sun City West",
        "Prescott Valley",
    ]

# Chambers are US-only; skip for other countries
CHAMBER_DIRECTORIES = [
    "https://business.phoenixchamber.com",
    "https://business.scottsdalechamber.com",
    "https://business.chandlerchamber.com",
    "https://business.flagstaffchamber.com",
] if COUNTRY.upper() in ("USA", "US", "UNITED STATES") else []

NICHE_MAP: dict[str, list[str]] = {
    "Dentists": [
        "dentist",
        "dental office",
        "orthodontist",
        "oral surgeon",
        "periodontist",
        "endodontist",
        "pediatric dentist",
    ],
    "Gyms / Fitness centers": [
        "gym",
        "fitness center",
        "personal trainer",
        "boot camp",
        "martial arts",
        "boxing gym",
        "health club",
    ],
    "Real estate agencies": [
        "real estate agency",
        "real estate",
        "property management",
        "commercial real estate",
        "investment property",
    ],
    "Clinics / med spas": [
        "clinic",
        "med spa",
        "urgent care",
        "dermatology",
        "plastic surgery",
        "veterinary clinic",
        "chiropractic",
        "physical therapy",
        "pediatrics",
        "family medicine",
        "obgyn",
        "cardiology",
        "orthopedics",
    ],
    "HVAC / contractors": [
        "hvac contractor",
        "contractor",
        "home builder",
        "remodeling",
        "landscaping",
        "pool builder",
        "solar installer",
        "handyman",
        "electrician",
        "plumber",
        "flooring",
        "painter",
        "window installer",
    ],
    "Law firms": [
        "law firm",
        "lawyer",
        "personal injury attorney",
        "criminal defense",
        "family law",
        "divorce attorney",
        "immigration lawyer",
        "estate planning",
        "bankruptcy attorney",
        "dui lawyer",
    ],
}

NICHE_KEYWORDS = [
    "dent", "dental", "orthodont", "oral", "periodont", "endodont",
    "pediatric dentist", "clinic", "med spa", "medical", "medspa",
    "urgent care", "dermatolog", "plastic surgery", "veterinar",
    "chiroprac", "physical therap", "pediatric", "family medicine",
    "obgyn", "cardiolog", "orthopedic", "gym", "fitness", "workout",
    "training", "crossfit", "yoga", "pilates", "personal train",
    "boot camp", "martial art", "boxing", "health club", "real estate",
    "realty", "property", "realtor", "property management",
    "commercial real estate", "investment property", "hvac", "heating",
    "cooling", "construction", "contractor", "roof", "plumb", "electric",
    "home builder", "remodel", "landscap", "pool", "solar", "handyman",
    "flooring", "painter", "window", "law", "attorney", "legal", "lawyer",
    "personal injury", "criminal defense", "family law", "divorce",
    "immigration", "estate planning", "bankruptcy", "dui",
]

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}&num=10",
    "bing": "https://www.bing.com/search?q={query}&count=30",
    "yahoo": "https://search.yahoo.com/search?p={query}&n=30",
    "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
    "startpage": "https://www.startpage.com/sp/search?query={query}",
}

BLOCKLIST_DOMAINS = {
    "facebook.com", "linkedin.com", "twitter.com", "instagram.com",
    "pinterest.com", "tiktok.com", "youtube.com", "yelp.com", "bbb.org",
    "yellowpages.com", "superpages.com", "manta.com", "mapquest.com",
    "healthgrades.com", "avvo.com", "lawyers.com", "zillow.com",
    "realtor.com", "angieslist.com", "thumbtack.com", "homeadvisor.com",
    "porch.com", "houzz.com", "chamberofcommerce.com", "google.com",
    "bing.com", "yahoo.com", "duckduckgo.com",
    # Legal directories
    "justia.com", "bcgsearch.com", "martindale.com", "nolo.com",
    "findlaw.com", "superlawyers.com", "bestlawyers.com", "lawinfo.com",
    "legalmatch.com", "lawyer.com", "legalzoom.com", "rocketlawyer.com",
    "upcounsel.com", "lawpath.com", "lawdepot.com", "naca.net",
    # Job boards / aggregators
    "ziprecruiter.com", "indeed.com", "glassdoor.com", "monster.com",
    "careerbuilder.com", "simplyhired.com", "snagajob.com",
    # Government / courts
    "azcourts.gov",
    # Universities hosting directories
    "cornell.edu",
    # General directories
    "yellowbook.com", "local.com", "citysearch.com", "merchantcircle.com",
    "foursquare.com", "tripadvisor.com", "whitepages.com",
}

CHAMBER_DOMAINS = {
    "phoenixchamber.com", "scottsdalechamber.com",
    "chandlerchamber.com", "flagstaffchamber.com",
}

RELEVANT_SCHEMA_TYPES = {
    "LocalBusiness", "Dentist", "LegalService", "Attorney", "Lawyer",
    "MedicalClinic", "HealthAndBeautyBusiness", "MedicalBusiness",
    "RealEstateAgent", "GymOrExerciseName", "FitnessAndNutrition",
    "HVACBusiness", "HomeAndConstructionBusiness", "ProfessionalService",
    "Organization", "Place", "Person", "Dentistry", "LegalOffice",
    "RealEstateOffice", "Gym", "ExerciseGym",
}

SCHEMA_TYPE_TO_NICHE = {
    "Dentist": "Dentists",
    "Dentistry": "Dentists",
    "LegalService": "Law firms",
    "Attorney": "Law firms",
    "Lawyer": "Law firms",
    "LegalOffice": "Law firms",
    "MedicalClinic": "Clinics / med spas",
    "HealthAndBeautyBusiness": "Clinics / med spas",
    "MedicalBusiness": "Clinics / med spas",
    "RealEstateAgent": "Real estate agencies",
    "RealEstateOffice": "Real estate agencies",
    "GymOrExerciseName": "Gyms / Fitness centers",
    "Gym": "Gyms / Fitness centers",
    "ExerciseGym": "Gyms / Fitness centers",
    "FitnessAndNutrition": "Gyms / Fitness centers",
    "HVACBusiness": "HVAC / contractors",
    "HomeAndConstructionBusiness": "HVAC / contractors",
    "ProfessionalService": "HVAC / contractors",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
# International-friendly phone regex: +CC prefix optional, then 7-15 digits with separators
PHONE_RE = re.compile(
    r"(?:\+[\d]{1,3}[\s.\-]?)?(?:\(?\d{1,4}\)?[\s.\-]?)?\d{1,4}[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}",
    re.IGNORECASE,
)
OWNER_RE_PATTERNS = [
    re.compile(
        r"(?:Owner|Founder|Principal|CEO|Managing\s+Director)[\s:]+([A-Z][a-zA-Z\-\.]+\s+[A-Z][a-zA-Z\-\.]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:Dr\.?|Mr\.?|Ms\.?|Mrs\.?)\s+([A-Z][a-zA-Z\-\.]+\s+[A-Z][a-zA-Z\-\.]+).*?(?:Owner|Founder|Principal)",
        re.IGNORECASE,
    ),
]

CRAWL_PATHS = [
    "",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/staff",
    "/locations",
    "/our-office",
    "/meet-the-team",
    "/leadership",
    "/directory",
    "/who-we-are",
    "/company",
    "/services",
    "/get-in-touch",
    "/reach-out",
    "/privacy",
    "/privacy-policy",
    "/book",
    "/book-appointment",
    "/appointment",
    "/request-appointment",
    "/schedule",
    "/office",
    "/our-doctors",
    "/meet-the-doctors",
    "/providers",
    "/physicians",
    "/dentists",
    "/attorneys",
    "/lawyers",
    "/partners",
]

COMMON_EMAIL_PREFIXES = [
    "info",
    "contact",
    "hello",
    "admin",
    "support",
    "office",
    "sales",
    "appointments",
    "booking",
    "help",
    "service",
    "frontdesk",
    "reception",
    "inquiry",
    "questions",
]

FALLBACK_PATHS = ["/contact", "/about", "/privacy", "/contact-us", "/about-us"]

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff", ".tif"
}

GENERIC_TITLES = {
    "contact us", "contact", "about us", "about", "team", "staff",
    "our people", "meet the team", "leadership", "home", "welcome",
    "employer help center", "help center", "careers", "jobs",
    "apply now", "login", "sign in", "privacy policy", "terms of service",
    "terms and conditions", "sitemap", "404", "page not found",
    "error", "forbidden", "access denied", "blog", "news", "events",
    "resources", "faq", "frequently asked questions", "testimonials",
    "reviews", "gallery", "portfolio", "products", "shop", "store",
    "cart", "checkout", "search", "results", "site map", "index",
}


def get_progress_file() -> Path:
    """Return a region-specific progress file path."""
    country = COUNTRY.upper()
    if country in ("USA", "US", "UNITED STATES"):
        region_slug = STATE.lower().replace(" ", "_")
    else:
        region_slug = COUNTRY.lower().replace(" ", "_")
    return OUTPUT_DIR / f"{region_slug}_progress.json"
