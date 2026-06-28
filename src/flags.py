"""Country -> flag code map, shared by the site and the local input tool.

Values are the codes flagcdn.com serves images for: ISO 3166-1 alpha-2 (lower
case), plus the UK home-nation subdivisions (gb-eng / gb-sct / gb-wls / gb-nir).
Build a flag URL as ``https://flagcdn.com/{w}x{h}/{code}.png``.

Keys are human-readable canonical names plus common aliases. Lookups should be
case/accent/punctuation-insensitive (see ``normalize``), so "Cote d'Ivoire",
"Côte d'Ivoire" and "Ivory Coast" all resolve. Group-position placeholders in the
fixtures ("Winner E", "Runner-up A", "3rd A/B/C/D/F") match nothing and render no
flag, which is the desired behaviour until real teams are slotted in.

Stdlib only — no third-party dependencies.
"""
import re
import unicodedata

# Canonical name (and a few aliases) -> flagcdn code.
FLAGS = {
    # Hosts
    "United States": "us", "USA": "us", "United States of America": "us",
    "Canada": "ca", "Mexico": "mx",
    # CONMEBOL
    "Argentina": "ar", "Brazil": "br", "Uruguay": "uy", "Colombia": "co",
    "Ecuador": "ec", "Peru": "pe", "Chile": "cl", "Paraguay": "py",
    "Bolivia": "bo", "Venezuela": "ve",
    # UEFA
    "France": "fr", "Spain": "es", "Portugal": "pt", "England": "gb-eng",
    "Netherlands": "nl", "Belgium": "be", "Germany": "de", "Italy": "it",
    "Croatia": "hr", "Switzerland": "ch", "Denmark": "dk", "Serbia": "rs",
    "Poland": "pl", "Austria": "at", "Turkey": "tr", "Turkiye": "tr",
    "Ukraine": "ua", "Czechia": "cz", "Czech Republic": "cz", "Scotland": "gb-sct",
    "Wales": "gb-wls", "Northern Ireland": "gb-nir", "Republic of Ireland": "ie",
    "Ireland": "ie", "Greece": "gr", "Hungary": "hu", "Romania": "ro",
    "Norway": "no", "Sweden": "se", "Finland": "fi", "Iceland": "is",
    "Slovakia": "sk", "Slovenia": "si", "Albania": "al", "North Macedonia": "mk",
    "Georgia": "ge", "Bosnia and Herzegovina": "ba", "Bosnia": "ba",
    "Montenegro": "me", "Bulgaria": "bg", "Russia": "ru", "Kosovo": "xk",
    "Luxembourg": "lu", "Israel": "il",
    # AFC
    "Japan": "jp", "South Korea": "kr", "Korea Republic": "kr",
    "Korea DPR": "kp", "North Korea": "kp", "Iran": "ir", "IR Iran": "ir",
    "Australia": "au", "Saudi Arabia": "sa", "Qatar": "qa",
    "United Arab Emirates": "ae", "UAE": "ae", "Iraq": "iq", "Jordan": "jo",
    "Uzbekistan": "uz", "China": "cn", "China PR": "cn", "Oman": "om",
    "Bahrain": "bh", "Kuwait": "kw", "Thailand": "th", "Vietnam": "vn",
    "India": "in", "Indonesia": "id", "Palestine": "ps",
    # CAF
    "Senegal": "sn", "Morocco": "ma", "Tunisia": "tn", "Ghana": "gh",
    "Cameroon": "cm", "Nigeria": "ng", "Egypt": "eg", "Algeria": "dz",
    "Ivory Coast": "ci", "Cote d'Ivoire": "ci", "Mali": "ml",
    "South Africa": "za", "Burkina Faso": "bf", "DR Congo": "cd",
    "Congo DR": "cd", "Congo": "cg", "Gabon": "ga", "Cape Verde": "cv",
    "Cabo Verde": "cv", "Guinea": "gn", "Angola": "ao", "Zambia": "zm",
    "Kenya": "ke", "Equatorial Guinea": "gq", "Benin": "bj", "Gambia": "gm",
    "Mauritania": "mr", "Mozambique": "mz", "Uganda": "ug", "Tanzania": "tz",
    "Madagascar": "mg", "Namibia": "na", "Sudan": "sd", "Libya": "ly",
    "Togo": "tg", "Sierra Leone": "sl", "Zimbabwe": "zw", "Ethiopia": "et",
    # CONCACAF
    "Costa Rica": "cr", "Panama": "pa", "Honduras": "hn", "Jamaica": "jm",
    "El Salvador": "sv", "Guatemala": "gt", "Haiti": "ht",
    "Trinidad and Tobago": "tt", "Curacao": "cw", "Suriname": "sr",
    # OFC
    "New Zealand": "nz", "Fiji": "fj", "Tahiti": "pf",
    "Solomon Islands": "sb", "New Caledonia": "nc", "Papua New Guinea": "pg",
}


def normalize(name):
    """Lower-case, strip accents and non-alphanumerics for tolerant matching."""
    s = unicodedata.normalize("NFD", str(name or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# Normalized-key view, handy for any server-side lookups/tests.
NORM_FLAGS = {normalize(k): v for k, v in FLAGS.items()}


def flag_code(name):
    """Return the flagcdn code for a team name, or None if unknown/placeholder."""
    return NORM_FLAGS.get(normalize(name))
