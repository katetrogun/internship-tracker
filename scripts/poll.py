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
    r"\b(business|marketing|management|strategy|operations|sales|brand|growth|"
    r"biz ?ops|communications|finance|consulting)\b",
    re.IGNORECASE,
)


def matches(title):
    return bool(INTERN_RE.search(title)) and bool(CATEGORY_RE.search(title))


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
        jobs.append({
            "id": f"greenhouse:{slug}:{job['id']}",
            "title": title,
            "location": (job.get("location") or {}).get("name", ""),
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
        created = job.get("createdAt")
        updated_at = (
            datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            if created else ""
        )
        jobs.append({
            "id": f"lever:{slug}:{job['id']}",
            "title": title,
            "location": cats.get("location", ""),
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
