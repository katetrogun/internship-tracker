# Internship Tracker

A free, self-updating tracker for business/marketing/management internships.
It polls the public job-board APIs that companies use (Greenhouse, Lever),
filters for internship titles matching business/marketing/management, and
publishes the results to a simple webpage.

## How it works

- `companies.json` — the list of companies to watch, with their ATS
  ("greenhouse" or "lever") and board slug.
- `scripts/poll.py` — fetches each company's public job board, keeps only
  postings whose title contains "intern"/"internship" AND a
  business/marketing/management-related word, and writes the result to
  `data.json` (tracking when each posting was first seen).
- `index.html` — a static page that reads `data.json` and displays the
  postings, newest first, with a "NEW" badge for anything seen in the last
  48 hours.
- `.github/workflows/poll.yml` — runs `poll.py` every 30 minutes on GitHub's
  free Actions runners and commits the updated `data.json` back to the repo.

Nothing needs to run on your own computer — GitHub's servers do the checking
for you, for free.

## One-time setup

1. **Create a GitHub repo.** It must be **public** for GitHub Pages to be
   free. This only contains public job posting data, so that's fine.
   ```bash
   cd ~/internship-tracker
   git init
   git add .
   git commit -m "Initial internship tracker"
   ```
   Then create a new repo on github.com (no README/license, since this
   already has files) and push:
   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```

2. **Enable GitHub Pages.** In the repo on github.com: Settings → Pages →
   under "Build and deployment", set Source to "Deploy from a branch",
   branch `main`, folder `/ (root)`. Save. GitHub will give you a URL like
   `https://<your-username>.github.io/<repo-name>/` — that's your site.

3. **Enable the scheduled check.** Actions should already be enabled by
   default. To confirm it works right away instead of waiting 30 minutes,
   go to the Actions tab → "Poll internship boards" → "Run workflow".

That's it — the page will now pick up new postings within 30 minutes of
them going live, automatically.

## Adding more companies

Not every company uses Greenhouse or Lever, and this seed list is small.
To add one:

1. Check its careers page — if it's built on Greenhouse, the URL usually
   looks like `boards.greenhouse.io/<slug>` or the footer says "powered by
   Greenhouse". For Lever, `jobs.lever.co/<slug>`.
2. Verify the slug works by opening it directly:
   - Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`
   - Lever: `https://api.lever.co/v0/postings/<slug>?mode=json`
   If you get JSON back (not a 404), the slug is correct.
3. Add an entry to `companies.json`:
   ```json
   { "name": "Company Name", "ats": "greenhouse", "slug": "the-slug" }
   ```
4. Commit and push. The next scheduled run will pick it up.

Companies that use their own in-house application system (not Greenhouse
or Lever) can't be tracked this way — that would require custom scraping
per company, which is much more fragile.

## Limitations

- Only catches companies on Greenhouse or Lever job boards.
- GitHub disables scheduled workflows on a repo after 60 days with no
  commits/activity — pushing any small change (or manually running the
  workflow) re-enables it. Since this workflow commits to the repo itself
  whenever data changes, this is rarely an issue in practice.
- Scheduled workflow runs can occasionally be delayed by a few minutes
  during high load on GitHub's shared runners — "every 30 minutes" is a
  target, not a guarantee.
- The internship keyword filter is intentionally broad (business,
  marketing, management, strategy, operations, sales, brand, growth,
  communications, finance, consulting). Edit the `CATEGORY_RE` regex in
  `scripts/poll.py` to narrow or widen it.

## Running locally (optional)

```bash
python3 scripts/poll.py   # updates data.json
python3 -m http.server     # then open http://localhost:8000
```
