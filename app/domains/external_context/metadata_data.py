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
    {"value": "math", "label": "Mathematics"},
    {"value": "science", "label": "Science"},
    {"value": "ela", "label": "English Language Arts"},
    {"value": "social_studies", "label": "Social Studies"},
    {"value": "history", "label": "History"},
    {"value": "geography", "label": "Geography"},
    {"value": "art", "label": "Art"},
    {"value": "music", "label": "Music"},
    {"value": "pe", "label": "Physical Education"},
    {"value": "foreign_language", "label": "Foreign Language"},
    {"value": "computer_science", "label": "Computer Science"},
    {"value": "other", "label": "Other"},
]

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
