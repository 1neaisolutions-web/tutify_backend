"""
Static metadata for countries, regions, subjects, curriculums, grade bands.
Replace with DB or external APIs later (NCES, government APIs, etc.).
"""

# Countries (sample; expand via backend /metadata/countries)
COUNTRIES = [
    {"value": "US", "label": "United States"},
    {"value": "GB", "label": "United Kingdom"},
    {"value": "CA", "label": "Canada"},
    {"value": "AU", "label": "Australia"},
    {"value": "IN", "label": "India"},
    {"value": "DE", "label": "Germany"},
    {"value": "FR", "label": "France"},
    {"value": "SG", "label": "Singapore"},
    {"value": "IE", "label": "Ireland"},
    {"value": "NZ", "label": "New Zealand"},
    {"value": "ZA", "label": "South Africa"},
    {"value": "OTHER", "label": "Other"},
]

# Regions by country (static for now)
REGIONS_BY_COUNTRY = {
    "US": [
        {"value": "AL", "label": "Alabama"},
        {"value": "AK", "label": "Alaska"},
        {"value": "AZ", "label": "Arizona"},
        {"value": "AR", "label": "Arkansas"},
        {"value": "CA", "label": "California"},
        {"value": "CO", "label": "Colorado"},
        {"value": "CT", "label": "Connecticut"},
        {"value": "DE", "label": "Delaware"},
        {"value": "FL", "label": "Florida"},
        {"value": "GA", "label": "Georgia"},
        {"value": "HI", "label": "Hawaii"},
        {"value": "ID", "label": "Idaho"},
        {"value": "IL", "label": "Illinois"},
        {"value": "IN", "label": "Indiana"},
        {"value": "IA", "label": "Iowa"},
        {"value": "KS", "label": "Kansas"},
        {"value": "KY", "label": "Kentucky"},
        {"value": "LA", "label": "Louisiana"},
        {"value": "ME", "label": "Maine"},
        {"value": "MD", "label": "Maryland"},
        {"value": "MA", "label": "Massachusetts"},
        {"value": "MI", "label": "Michigan"},
        {"value": "MN", "label": "Minnesota"},
        {"value": "MS", "label": "Mississippi"},
        {"value": "MO", "label": "Missouri"},
        {"value": "MT", "label": "Montana"},
        {"value": "NE", "label": "Nebraska"},
        {"value": "NV", "label": "Nevada"},
        {"value": "NH", "label": "New Hampshire"},
        {"value": "NJ", "label": "New Jersey"},
        {"value": "NM", "label": "New Mexico"},
        {"value": "NY", "label": "New York"},
        {"value": "NC", "label": "North Carolina"},
        {"value": "ND", "label": "North Dakota"},
        {"value": "OH", "label": "Ohio"},
        {"value": "OK", "label": "Oklahoma"},
        {"value": "OR", "label": "Oregon"},
        {"value": "PA", "label": "Pennsylvania"},
        {"value": "RI", "label": "Rhode Island"},
        {"value": "SC", "label": "South Carolina"},
        {"value": "SD", "label": "South Dakota"},
        {"value": "TN", "label": "Tennessee"},
        {"value": "TX", "label": "Texas"},
        {"value": "UT", "label": "Utah"},
        {"value": "VT", "label": "Vermont"},
        {"value": "VA", "label": "Virginia"},
        {"value": "WA", "label": "Washington"},
        {"value": "WV", "label": "West Virginia"},
        {"value": "WI", "label": "Wisconsin"},
        {"value": "WY", "label": "Wyoming"},
        {"value": "DC", "label": "District of Columbia"},
    ],
    "GB": [
        {"value": "ENG", "label": "England"},
        {"value": "SCT", "label": "Scotland"},
        {"value": "WLS", "label": "Wales"},
        {"value": "NIR", "label": "Northern Ireland"},
    ],
    "CA": [
        {"value": "AB", "label": "Alberta"},
        {"value": "BC", "label": "British Columbia"},
        {"value": "MB", "label": "Manitoba"},
        {"value": "NB", "label": "New Brunswick"},
        {"value": "NL", "label": "Newfoundland and Labrador"},
        {"value": "NS", "label": "Nova Scotia"},
        {"value": "NT", "label": "Northwest Territories"},
        {"value": "NU", "label": "Nunavut"},
        {"value": "ON", "label": "Ontario"},
        {"value": "PE", "label": "Prince Edward Island"},
        {"value": "QC", "label": "Quebec"},
        {"value": "SK", "label": "Saskatchewan"},
        {"value": "YT", "label": "Yukon"},
    ],
    "AU": [
        {"value": "ACT", "label": "Australian Capital Territory"},
        {"value": "NSW", "label": "New South Wales"},
        {"value": "NT", "label": "Northern Territory"},
        {"value": "QLD", "label": "Queensland"},
        {"value": "SA", "label": "South Australia"},
        {"value": "TAS", "label": "Tasmania"},
        {"value": "VIC", "label": "Victoria"},
        {"value": "WA", "label": "Western Australia"},
    ],
    "IN": [
        {"value": "AP", "label": "Andhra Pradesh"},
        {"value": "KA", "label": "Karnataka"},
        {"value": "KL", "label": "Kerala"},
        {"value": "MH", "label": "Maharashtra"},
        {"value": "TN", "label": "Tamil Nadu"},
        {"value": "OTHER", "label": "Other State"},
    ],
    "DE": [{"value": "BY", "label": "Bavaria"}, {"value": "NW", "label": "North Rhine-Westphalia"}, {"value": "OTHER", "label": "Other"}],
    "FR": [{"value": "IDF", "label": "Île-de-France"}, {"value": "OTHER", "label": "Other"}],
    "SG": [{"value": "CENTRAL", "label": "Central"}, {"value": "OTHER", "label": "Other"}],
    "IE": [{"value": "LEINSTER", "label": "Leinster"}, {"value": "MUNSTER", "label": "Munster"}, {"value": "OTHER", "label": "Other"}],
    "NZ": [{"value": "AUK", "label": "Auckland"}, {"value": "WLG", "label": "Wellington"}, {"value": "OTHER", "label": "Other"}],
    "ZA": [{"value": "WC", "label": "Western Cape"}, {"value": "GP", "label": "Gauteng"}, {"value": "OTHER", "label": "Other"}],
}

# Default regions when country not in map
DEFAULT_REGIONS = [{"value": "OTHER", "label": "Other"}]

SUBJECTS = [
    {"value": "math", "label": "Mathematics", "teacher_tools": "Mathematics", "template": "Math"},
    {"value": "science", "label": "Science", "teacher_tools": "Science", "template": "Science"},
    {"value": "ela", "label": "English Language Arts", "teacher_tools": "English", "template": "English"},
    {"value": "social_studies", "label": "Social Studies", "template": "General"},
    {"value": "history", "label": "History", "teacher_tools": "History", "template": "General"},
    {"value": "geography", "label": "Geography", "teacher_tools": "Geography", "template": "General"},
    {"value": "biology", "label": "Biology", "teacher_tools": "Biology", "template": "Science"},
    {"value": "physics", "label": "Physics", "teacher_tools": "Physics", "template": "Science"},
    {"value": "chemistry", "label": "Chemistry", "teacher_tools": "Chemistry", "template": "Science"},
    {"value": "art", "label": "Art", "template": "Arts"},
    {"value": "music", "label": "Music"},
    {"value": "pe", "label": "Physical Education"},
    {"value": "foreign_language", "label": "Foreign Language"},
    {"value": "computer_science", "label": "Computer Science", "teacher_tools": "Computer Science", "template": "Technology"},
    {"value": "other", "label": "Other", "template": "General"},
]

# Legacy subject strings → canonical SUBJECTS value (keys lowercased)
SUBJECT_ALIASES: dict[str, str] = {
    "mathematics": "math",
    "math": "math",
    "english": "ela",
    "english language arts": "ela",
    "science": "science",
    "biology": "biology",
    "physics": "physics",
    "chemistry": "chemistry",
    "history": "history",
    "geography": "geography",
    "computer science": "computer_science",
    "social studies": "social_studies",
    "arts": "art",
    "art": "art",
    "technology": "computer_science",
    "business": "other",
    "general": "other",
    "physical education": "pe",
}

CURRICULUM_FRAMEWORKS = [
    {"value": "national_curriculum", "label": "National Curriculum"},
    {"value": "common_core", "label": "Common Core"},
    {"value": "ib", "label": "IB"},
    {"value": "cambridge", "label": "Cambridge"},
    {"value": "state_board", "label": "State Board"},
    {"value": "other", "label": "Other"},
]

GRADE_BANDS = [
    {"value": "K-2", "label": "K–2"},
    {"value": "3-5", "label": "3–5"},
    {"value": "6-8", "label": "6–8"},
    {"value": "9-12", "label": "9–12"},
    {"value": "higher_ed", "label": "Higher Education"},
    {"value": "other", "label": "Other"},
]

# US K-12 individual grades — canonical list for all dropdowns
US_GRADES = [
    {"value": "K", "label": "Kindergarten", "numeric": 0, "band": "K-2"},
    {"value": "1", "label": "Grade 1", "numeric": 1, "band": "K-2"},
    {"value": "2", "label": "Grade 2", "numeric": 2, "band": "K-2"},
    {"value": "3", "label": "Grade 3", "numeric": 3, "band": "3-5"},
    {"value": "4", "label": "Grade 4", "numeric": 4, "band": "3-5"},
    {"value": "5", "label": "Grade 5", "numeric": 5, "band": "3-5"},
    {"value": "6", "label": "Grade 6", "numeric": 6, "band": "6-8"},
    {"value": "7", "label": "Grade 7", "numeric": 7, "band": "6-8"},
    {"value": "8", "label": "Grade 8", "numeric": 8, "band": "6-8"},
    {"value": "9", "label": "Grade 9", "numeric": 9, "band": "9-12"},
    {"value": "10", "label": "Grade 10", "numeric": 10, "band": "9-12"},
    {"value": "11", "label": "Grade 11", "numeric": 11, "band": "9-12"},
    {"value": "12", "label": "Grade 12", "numeric": 12, "band": "9-12"},
]

# Legacy alias map — keys are lowercased raw stored values, values are canonical US_GRADES value
GRADE_ALIASES: dict[str, str] = {
    # UK Year naming
    "year 1": "1",
    "year 2": "2",
    "year 3": "3",
    "year 4": "4",
    "year 5": "5",
    "year 6": "6",
    "year 7": "7",
    "year 8": "8",
    "year 9": "9",
    "year 10": "10",
    "year 11": "11",
    "year 12": "12",
    # "Grade X" strings (guard against casing)
    "grade 1": "1",
    "grade 2": "2",
    "grade 3": "3",
    "grade 4": "4",
    "grade 5": "5",
    "grade 6": "6",
    "grade 7": "7",
    "grade 8": "8",
    "grade 9": "9",
    "grade 10": "10",
    "grade 11": "11",
    "grade 12": "12",
    "grade k": "K",
    # Bare numbers stored as strings
    "0": "K",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
    "10": "10",
    "11": "11",
    "12": "12",
    # Kindergarten variants
    "kindergarten": "K",
    "k": "K",
    "kinder": "K",
    # Template ordinal enums (seed_templates.py grade_level)
    "1st grade": "1",
    "2nd grade": "2",
    "3rd grade": "3",
    "4th grade": "4",
    "5th grade": "5",
    "6th grade": "6",
    "7th grade": "7",
    "8th grade": "8",
    "9th grade": "9",
    "10th grade": "10",
    "11th grade": "11",
    "12th grade": "12",
}

# Legacy grade band aliases — keys lowercased, values canonical GRADE_BANDS value
GRADE_BAND_ALIASES: dict[str, str] = {
    "k-5": "K-2",
    "k-2": "K-2",
    "3-5": "3-5",
    "grades 3-5": "3-5",
    "6-8": "6-8",
    "grades 6-8": "6-8",
    "9-10": "9-12",
    "9-12": "9-12",
    "grades 9-10": "9-12",
    "grades 11-12": "9-12",
    "higher education": "higher_ed",
    "higher_ed": "higher_ed",
    "elementary (k-5)": "K-2",
    "middle school (6-8)": "6-8",
    "high school (9-12)": "9-12",
    "college": "higher_ed",
    "ms": "6-8",
    "hs": "9-12",
    "middle school": "6-8",
    "high school": "9-12",
    "elementary (3-5)": "3-5",
}

SCHOOL_TYPES = [
    {"value": "public", "label": "Public"},
    {"value": "private", "label": "Private"},
    {"value": "charter", "label": "Charter"},
    {"value": "international", "label": "International"},
    {"value": "other", "label": "Other"},
]

LANGUAGES = [
    {"value": "en", "label": "English"},
    {"value": "es", "label": "Spanish"},
    {"value": "fr", "label": "French"},
    {"value": "de", "label": "German"},
    {"value": "other", "label": "Other"},
]

YEARS_EXPERIENCE = [
    {"value": "0-2", "label": "0–2"},
    {"value": "3-5", "label": "3–5"},
    {"value": "6-10", "label": "6–10"},
    {"value": "10+", "label": "10+"},
]


def get_regions_for_country(country_code: str) -> list:
    """Return list of {value, label} for the given country."""
    return REGIONS_BY_COUNTRY.get(country_code, DEFAULT_REGIONS)
