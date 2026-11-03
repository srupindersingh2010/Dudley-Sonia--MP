# Dudley public information — Sonia Kumar MP

Independent public information prototype run by Rupinder Singh, inspired by [Lower Stoke](https://www.lowerstoke.co.uk/) ([source repository](https://github.com/srupindersingh2010/lowerstoke)). This is **not the MP’s official website**. Office approval has not been confirmed. English only. No private diary, casework form, subscriber database, tracking or API keys.

## Website address and first publication

Expected GitHub Pages address after deployment:

**https://srupindersingh2010.github.io/Dudley-Sonia--MP/**

1. Open this repository’s **Settings → Pages**.
2. Under **Build and deployment → Source**, select **GitHub Actions** (not “Deploy from a branch”). No domain is needed; do not copy Lower Stoke’s CNAME.
3. In **Actions**, enable workflows if GitHub asks. Open **Daily public information and GitHub Pages → Run workflow → main → Run workflow**.
4. If the update cannot commit snapshots, check **Settings → Actions → General → Workflow permissions** and allow read/write repository permissions where your account policy permits. The workflow declares only the permissions each job needs.
5. Wait for the deploy job to finish. The Pages environment and Settings → Pages will show the live URL. Until a deployment succeeds, the expected address can return 404.

GitHub Free supports Pages for public repositories. GitHub scheduling is best-effort: 07:00 is the scheduled time, not a guarantee of exact start or publication. Scheduled workflows can be disabled after 60 days with no repository activity; successful daily data commits normally provide activity. Monitor Actions for errors. Source: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Daily updates

Two UTC cron entries plus a tested Europe/London clock gate select exactly one scheduled daily data run: 06:00 UTC during BST, 07:00 UTC during GMT. This preserves 07:00 UK local time, including transition dates. Manual runs and pushes to main also update and deploy. A delayed run still selects the nominal correct schedule.

Each source writes `/data/<source>.json` with `retrieved_at`, `checked_at`, `source`, `status`, and `data`. On failure, the last successful payload and retrieval date remain unchanged. A never-successful source shows an explicit unavailable notice and an official link. Empty valid responses are distinguished from fetch failures. Multi-source news retains each RSS feed separately; council committee schedules retain each sub-source separately. Current-window sections filter old dates at build time rather than passing past meetings off as upcoming.

`build.py` generates complete static HTML into `dist/`. All content and navigation work without JavaScript. Only `dist/` is uploaded to Pages; private caches, scripts and configuration are not deployed as web assets. Source code remains public in this repository. There are no API keys. If adding a provider requiring one later, use an Actions Secret and never output it or its authenticated URL into public JSON.

## What the MP’s office needs to do

**Nothing is required to connect a diary.** Rupinder requested public information only: no private calendar will be connected or published.

- Continue publishing event announcements on the MP’s official website or linked public accounts.
- The site links directly to those official routes. A public website RSS feed is checked daily, but currently blocks automated access (HTTP 403); newspaper/Google News and BBC RSS supplement the linked headlines.
- Announcements in news have **publication dates**, not inferred event dates. We do not automatically turn articles into future surgery appointments or assume the MP attends council/community events.
- Public council and WMCA meeting dates update from their published schedules. Past agendas/minutes are linked through the official archives.
- To make future MP events appear as dated event cards, a maintainer would need to add a verified public-only events feed and a date-aware parser. That is intentionally not a private-office diary integration and is not configured in this build.
- Office endorsement, an “official” label, newsletters, new languages, or casework collection require a separate explicit change. Do not imply endorsement merely by changing the title.

## Coverage and source audit

Read [SOURCE-AUDIT.md](SOURCE-AUDIT.md) for actual working endpoints, day-one gaps and reporting definitions. The site’s Sources & Status page and JSON files show live retrieval status. Some sources update monthly or annually rather than daily. Third-party news is linked and attributed, not copied.

Parliament ID **5274**; constituency ID **4019**; ONS current-constituency code **E14001204**. Council: Dudley MBC; combined authority: WMCA; police: West Midlands Police.

Voting records are shown as **recorded voting participation**, never presented as an attendance rate. Crime uses Parliament’s approximate constituency geometry and anonymised police locations. Employment and claimant figures are scoped to the current constituency; no borough substitution.

## Local maintenance

Python 3.12+:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch.py
python -m unittest discover -s tests -v
python scripts/build.py
python scripts/check_site.py
python -m http.server 8000 --directory dist
```

Refresh selected sources with `python scripts/fetch.py --only votes news`. HTTP requests require network access. A normal complete first petition scan may need around a thousand detail requests; bounded concurrency and a versioned cache reduce subsequent requests. The ranking does not impose an arbitrary national signature threshold.

Update templates in `templates/page.html`, styling in `assets/style.css`, and public operator settings in `config.json`. `/data` snapshots are committed; `.cache` is ignored and restored with Actions cache. Never store private casework in any file in this public repository.

## Attribution and accessibility

Contains Parliamentary information licensed under the [Open Parliament Licence v3.0](https://www.parliament.uk/site-information/copyright/open-parliament-licence/). Official portrait © UK Parliament, subject to the [Parliamentary Copyright Licence](https://www.parliament.uk/site-information/copyright-parliament/). ONS/Nomis and police datasets retain their stated Open Government Licence attribution. Publishers retain copyright in news headlines and linked articles. No portcullis logo is used.

Semantic pages, visible keyboard focus, skip link, high contrast, readable text, responsive layout, image alternatives, and a numerical alternative to the local SVG crime map are implemented. Automated structural checks are not a claim of independent WCAG 2.2 AA certification. See the site’s privacy and source notices.
