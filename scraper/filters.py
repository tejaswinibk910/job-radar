import re

from .seniority import classify

US_STATE_NAMES = r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|district of columbia"
US_CITIES = r"san francisco|bay area|seattle|boston|austin|chicago|los angeles|san jose|sunnyvale|mountain view|palo alto|menlo park|redmond|cupertino|santa clara|san diego|denver|atlanta|pittsburgh|nyc|brooklyn|rochester|cambridge, ma|ann arbor|raleigh|durham|dallas|houston|miami|philadelphia|portland|salt lake|boulder|irvine|detroit|minneapolis|washington,? d\.?c"
US_ABBR = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"

STRONG_US = re.compile(rf"united states|\busa\b|\bu\.s\.a?\b|\bus\b|\bu\.s\b|\b({US_STATE_NAMES})\b|\b({US_CITIES})\b", re.I)
ABBR_US = re.compile(rf"(,|\s-)\s*({US_ABBR})\b")  # case-sensitive on purpose: "Austin, TX"
NON_US = re.compile(
    r"\b(canada|toronto|vancouver|montreal|ontario|uk|united kingdom|england|london|ireland|dublin|"
    r"india|bangalore|bengaluru|hyderabad|pune|mumbai|delhi|gurgaon|chennai|germany|berlin|munich|"
    r"france|paris|netherlands|amsterdam|switzerland|zurich|poland|warsaw|spain|madrid|barcelona|"
    r"israel|tel aviv|singapore|japan|tokyo|korea|seoul|china|beijing|shanghai|taiwan|taipei|"
    r"australia|sydney|melbourne|mexico|brazil|argentina|colombia|emea|apac|latam|europe)\b",
    re.I,
)


def compile_list(patterns):
    return [re.compile(p, re.I) for p in patterns]


class Filters:
    def __init__(self, cfg):
        self.include = compile_list(cfg["title_include"])
        self.exclude = compile_list(cfg["title_exclude"])
        self.clearance = compile_list(cfg["clearance_patterns"])
        self.max_years = cfg["seniority"]["max_years"]

    def too_senior(self, job):
        return classify(job["title"], job["description"], self.max_years)[0] == "Senior"

    def title_ok(self, title):
        t = title or ""
        return any(p.search(t) for p in self.include) and not any(p.search(t) for p in self.exclude)

    def clearance_blocked(self, job):
        text = f"{job['title']} {job['description']}"
        return any(p.search(text) for p in self.clearance)

    @staticmethod
    def location_ok(loc, is_remote=False):
        """US or remote-US. Unknown/blank locations are kept so nothing gets missed."""
        loc = (loc or "").strip()
        if not loc:
            return True
        if STRONG_US.search(loc):
            return True
        non_us = NON_US.search(loc)
        if non_us:
            return False
        if ABBR_US.search(loc):
            return True
        if is_remote or re.search(r"remote|anywhere", loc, re.I):
            return True
        return True  # unrecognised (e.g. "Hybrid", "Multiple Locations") -> keep

    def keep(self, job):
        if job["source"] == "hackernews":
            role_ok = any(p.search(job["title"]) or p.search(job["description"][:600]) for p in self.include)
            return role_ok and self.location_ok(job["location"], job.get("is_remote")) \
                and not self.clearance_blocked(job) and not self.too_senior(job)
        return (
            self.title_ok(job["title"])
            and self.location_ok(job["location"], job.get("is_remote"))
            and not self.clearance_blocked(job)
            and not self.too_senior(job)
        )
