"""Classifies a posting as New Grad / Entry / Mid / Senior / Unknown."""
import re

TITLE_SENIOR = re.compile(r"\b(III|IV|V|VI)\b|\b(L|E|IC|P)[5-9]\b|\blevel\s*[3-9]\b|\bsr\b|\bsenior\b|\bstaff\b|"
                          r"\bprincipal\b|\blead\b|\bdistinguished\b|\bfellow\b")
TITLE_SENIOR_CI = re.compile(r"\bsenior\b|\bstaff\b|\bprincipal\b|\blead\b|\bmanager\b|\bdirector\b|\bhead of\b", re.I)
TITLE_ENTRY = re.compile(r"\bjunior\b|\bjr\.?\b|\bassociate\b|\b(I|1)\s*($|[,(\-|])|\bentry\b|\bgraduate\b", re.I)
NEW_GRAD = re.compile(r"new.?grad|new graduate|university grad|recent grad|college grad|early.?career|"
                      r"entry.?level|class of 202[6-8]|graduating (in|by)? ?(dec|december|spring|may|20)|"
                      r"campus hire|rotational program|0\s*[-–to]+\s*[12]\s*(\+\s*)?years", re.I)
YEARS = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)", re.I)


def min_years_required(text):
    found = []
    for m in YEARS.finditer(text or ""):
        window = text[max(0, m.start() - 80): m.end() + 80].lower()
        n = int(m.group(1))
        if "experience" in window and n <= 15:
            found.append(n)
    return min(found) if found else None


def classify(title, description, max_years=4):
    """Returns (level, min_years)."""
    title, desc = title or "", description or ""
    yrs = min_years_required(desc)
    if TITLE_SENIOR.search(title) or TITLE_SENIOR_CI.search(title):
        return "Senior", yrs
    if NEW_GRAD.search(title) or NEW_GRAD.search(desc[:4000]):
        return "New Grad", yrs
    if yrs is not None and yrs > max_years:
        return "Senior", yrs
    if TITLE_ENTRY.search(title) or (yrs is not None and yrs <= 2):
        return "Entry", yrs
    if yrs is not None:
        return "Mid", yrs
    return "Unknown", yrs
