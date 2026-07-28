#!/usr/bin/env python3
"""Polls public Greenhouse/Lever job boards for business/marketing/management
internship postings and writes the merged result to data.json.

Run manually with `python3 scripts/poll.py`, or on a schedule via the
GitHub Actions workflow in .github/workflows/poll.yml.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_FILE = ROOT / "companies.json"
DATA_FILE = ROOT / "data.json"

INTERN_RE = re.compile(r"\bintern(ship)?\b", re.IGNORECASE)
CATEGORY_RE = re.compile(
    r"\b(business( development)?|marketing|management|strategy|operations|sales|brand|"
    r"growth|biz ?ops|biz ?dev|communications|finance|consulting|revenue operations|"
    r"revops|customer success|account management|chief of staff|corporate development|"
    r"product marketing)\b",
    re.IGNORECASE,
)

US_STATE_ABBRS = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
US_STATE_RE = re.compile(r",\s*(" + US_STATE_ABBRS + r")\b")
US_WORD_RE = re.compile(r"\b(united states|usa|u\.s\.a?\.?)\b", re.IGNORECASE)
US_CITY_RE = re.compile(
    r"\b(new york|san francisco|los angeles|chicago|seattle|austin|boston|denver|"
    r"atlanta|miami|washington|san diego|san jose|portland|dallas|houston|phoenix|"
    r"philadelphia|nashville|salt lake city|minneapolis|detroit|bellevue|"
    r"mountain view|palo alto|menlo park)\b",
    re.IGNORECASE,
)
REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)

# Countries/regions/cities that show up often on these boards and are *not*
# the US. If any of these appear in the location string, we exclude the
# posting even if it also happens to mention "remote".
NON_US_RE = re.compile(
    r"\b(canada|toronto|vancouver|montreal|united kingdom|\buk\b|london|"
    r"ireland|dublin|germany|berlin|munich|france|paris|spain|madrid|barcelona|"
    r"italy|milan|rome|netherlands|amsterdam|poland|warsaw|portugal|lisbon|"
    r"india|bangalore|bengaluru|mumbai|delhi|hyderabad|pune|chennai|"
    r"singapore|australia|sydney|melbourne|japan|tokyo|china|shanghai|beijing|"
    r"brazil|sao paulo|mexico|philippines|manila|israel|tel aviv|egypt|cairo|"
    r"nigeria|lagos|kenya|nairobi|south africa|cape town|\buae\b|dubai|romania|"
    r"bucharest|ukraine|kyiv|sweden|stockholm|switzerland|zurich|belgium|"
    r"brussels|austria|vienna|czech|prague|colombia|bogota|argentina|"
    r"buenos aires|chile|santiago|new zealand|auckland|vietnam|indonesia|"
    r"jakarta|malaysia|kuala lumpur|thailand|bangkok|korea|seoul|taiwan|"
    r"taipei|hong kong|\bemea\b|\bapac\b|\blatam\b)\b",
    re.IGNORECASE,
)


def matches(title):
    return bool(INTERN_RE.search(title)) and bool(CATEGORY_RE.search(title))


def is_us_location(location):
    if not location:
        # No location listed at all — can't tell, so don't drop it.
        return True
    if NON_US_RE.search(location):
        return False
    if US_STATE_RE.search(location) or US_WORD_RE.search(location) or US_CITY_RE.search(location):
        return True
    if REMOTE_RE.search(location):
        # "Remote" with no country named and no non-US keyword matched.
        return True
    return False


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "internship-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_greenhouse(slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = fetch_json(url)
    jobs = []
    for job in data.get("jobs", []):
        title = job.get("title", "")
        if not matches(title):
            continue
        location = (job.get("location") or {}).get("name", "")
        if not is_us_location(location):
            continue
        jobs.append({
            "id": f"greenhouse:{slug}:{job['id']}",
            "title": title,
            "location": location,
            "url": job.get("absolute_url", ""),
            "updated_at": job.get("updated_at", ""),
        })
    return jobs


def fetch_lever(slug):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = fetch_json(url)
    jobs = []
    for job in data:
        title = job.get("text", "")
        if not matches(title):
            continue
        cats = job.get("categories", {}) or {}
        location = cats.get("location", "")
        if not is_us_location(location):
            continue
        created = job.get("createdAt")
        updated_at = (
            datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            if created else ""
        )
        jobs.append({
            "id": f"lever:{slug}:{job['id']}",
            "title": title,
            "location": location,
            "url": job.get("hostedUrl", ""),
            "updated_at": updated_at,
        })
    return jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever}


def main():
    companies = json.loads(COMPANIES_FILE.read_text())

    existing = {}
    if DATA_FILE.exists():
        prev = json.loads(DATA_FILE.read_text())
        for p in prev.get("postings", []):
            existing[p["id"]] = p

    now = datetime.now(timezone.utc).isoformat()
    all_jobs = []
    errors = []

    for company in companies:
        name, ats, slug = company["name"], company["ats"], company["slug"]
        fetcher = FETCHERS.get(ats)
        if fetcher is None:
            errors.append(f"{name}: unknown ats '{ats}'")
            continue

        try:
            jobs = fetcher(slug)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            errors.append(f"{name} ({slug}): {e}")
            # Transient failure: keep whatever we already had for this
            # company rather than dropping it from the site.
            all_jobs.extend(
                p for p in existing.values() if p["id"].startswith(f"{ats}:{slug}:")
            )
            continue

        for job in jobs:
            prev_posting = existing.get(job["id"])
            first_seen = prev_posting["first_seen"] if prev_posting else now
            all_jobs.append({**job, "company": name, "first_seen": first_seen})

    all_jobs.sort(key=lambda j: j["first_seen"], reverse=True)

    output = {"generated_at": now, "errors": errors, "postings": all_jobs}
    DATA_FILE.write_text(json.dumps(output, indent=2) + "\n")

    print(f"Wrote {len(all_jobs)} postings ({len(errors)} source errors).")
    for e in errors:
        print(f"  WARN: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
