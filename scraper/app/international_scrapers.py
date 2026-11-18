"""Dedicated scrapers for international job boards offering visa sponsorship and relocation support.

Platforms:
1. Arbeitnow (https://www.arbeitnow.com/api/job-board-api) - Developer JSON API for English-speaking jobs in Germany & EU.
2. Jobs4Internationals (https://jobs4internationals.de/) - German jobs curated for foreign internationals.
3. Relocate.me (https://relocate.me/) - Global tech job board where 100% of jobs include visa sponsorship & relocation assistance.
"""

import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from app.db import save_jobs
from app.filters import detect_language_requirements, detect_visa_sponsorship

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _clean_html_text(raw_html: str) -> str:
    """Strip HTML tags and unescape entities into clean readable text."""
    if not raw_html:
        return ""
    # Replace breaks and paragraphs with newlines
    text = re.sub(r"<(?:br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities
    text = html.unescape(text)
    # Normalize excessive newlines
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def scrape_arbeitnow(max_pages: int = 2) -> List[Dict[str, Any]]:
    """Scrape English-speaking / visa-friendly jobs from Arbeitnow's public developer API."""
    jobs: List[Dict[str, Any]] = []
    print("[Arbeitnow] Querying public job board API...")

    for page in range(1, max_pages + 1):
        url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    break
                payload = json.loads(resp.read().decode("utf-8"))
                page_jobs = payload.get("data", [])
                if not page_jobs:
                    break

                for item in page_jobs:
                    slug = item.get("slug") or ""
                    job_id = f"an-{slug}"
                    title = item.get("title") or ""
                    company = item.get("company_name") or ""
                    location = item.get("location") or "Germany"
                    job_url = item.get("url") or ""
                    raw_desc = item.get("description") or ""
                    clean_desc = _clean_html_text(raw_desc)

                    tags = item.get("tags") or []
                    tags_str = ", ".join(tags)

                    jobs.append({
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": job_url,
                        "description": clean_desc,
                        "search_keywords": f"arbeitnow, {tags_str}",
                    })
        except Exception as e:
            print(f"[Arbeitnow] Page {page} failed: {e}")
            break

    print(f"[Arbeitnow] Retrieved {len(jobs)} total jobs.")
    return jobs


def scrape_jobs4internationals() -> List[Dict[str, Any]]:
    """Scrape jobs from jobs4internationals.de via their Inertia.js dataset."""
    jobs: List[Dict[str, Any]] = []
    url = "https://jobs4internationals.de/?locale=en"
    print("[Jobs4Internationals] Fetching international listings...")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        m = re.search(r'data-page="([^"]+)"', content)
        if not m:
            print("[Jobs4Internationals] Could not find data-page attribute.")
            return jobs

        raw_json = html.unescape(m.group(1))
        page_data = json.loads(raw_json)
        job_list = page_data.get("props", {}).get("jobs", [])

        for item in job_list:
            # Skip roles strictly reserved for candidates who already possess EU work permits
            target_permit = item.get("target_audience_work_permit")
            if target_permit == "germany_eu":
                continue

            # Skip roles requiring C1 or C2 German
            german_level = item.get("language_level_german")
            if german_level in ("c1", "c2_native"):
                continue

            job_num = item.get("id") or item.get("nummer")
            job_id = f"j4i-{job_num}"
            title = item.get("full_title") or item.get("title") or ""
            org = item.get("organisation") or {}
            company = org.get("name") or "Employer"
            location = item.get("location") or "Germany"

            # Prefer canonical or direct link
            job_url = item.get("canonical_url") or item.get("link") or f"https://jobs4internationals.de/jobs/{job_num}"

            # Extract description from translated contents
            desc_text = ""
            translated = item.get("translated_contents") or []
            if translated and isinstance(translated, list):
                # Prefer English translation if available, otherwise first
                en_content = next((c for c in translated if c.get("locale") == "en"), translated[0])
                desc_text = _clean_html_text(en_content.get("description", ""))

            tags = item.get("tag_list") or []
            tags_str = ", ".join(tags)

            jobs.append({
                "job_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "description": desc_text,
                "search_keywords": f"jobs4internationals, {tags_str}",
            })
    except Exception as e:
        print(f"[Jobs4Internationals] Scrape failed: {e}")

    print(f"[Jobs4Internationals] Retrieved {len(jobs)} eligible jobs for foreign internationals.")
    return jobs


def scrape_relocate_me(
    queries: List[str] = None,
    max_jobs: int = 30,
) -> List[Dict[str, Any]]:
    """Scrape tech jobs with relocation and visa support from Relocate.me."""
    if queries is None:
        queries = ["frontend", "react", "fullstack", "python"]

    jobs: List[Dict[str, Any]] = []
    seen_links = set()
    print("[Relocate.me] Searching verified relocation & visa sponsorship jobs...")

    # Phase 1: Collect job URLs matching queries
    job_cards: List[Dict[str, str]] = []

    for q in queries:
        search_url = f"https://relocate.me/search?query={urllib.parse.quote(q)}"
        req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_content = resp.read().decode("utf-8", errors="replace")

            # Extract job cards: <div class="job__title"><a href="/.../..."><b>Title</b> in Location</a>
            matches = re.findall(
                r'<div class="job__title">\s*<a href="([^"]+)">\s*<b>([^<]+)</b>\s*in\s*([^<]+)</a>',
                html_content,
            )

            for rel_url, title, loc in matches:
                full_url = f"https://relocate.me{rel_url}" if rel_url.startswith("/") else rel_url
                if full_url not in seen_links:
                    seen_links.add(full_url)
                    job_cards.append({
                        "url": full_url,
                        "title": html.unescape(title.strip()),
                        "location": html.unescape(loc.strip()),
                        "query": q,
                    })
                    if len(job_cards) >= max_jobs:
                        break
        except Exception as e:
            print(f"[Relocate.me] Query '{q}' failed: {e}")

        if len(job_cards) >= max_jobs:
            break

    # Phase 2: Fetch detailed descriptions for discovered jobs
    for card in job_cards:
        j_url = card["url"]
        # Extract job_id from end of URL (e.g. -10256)
        id_match = re.search(r"-(\d+)$", j_url)
        job_id = f"rm-{id_match.group(1)}" if id_match else f"rm-{hash(j_url) & 0xffffffff}"

        # Extract company name from URL path (/country/city/company/role-id)
        url_parts = urllib.parse.urlparse(j_url).path.strip("/").split("/")
        company = url_parts[2].replace("-", " ").title() if len(url_parts) >= 3 else "Employer"

        desc = ""
        try:
            req = urllib.request.Request(j_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                detail_html = resp.read().decode("utf-8", errors="replace")

            # Extract job-content section
            m = re.search(r'<section\s+class="job-content">(.*?)</section>', detail_html, re.DOTALL)
            if m:
                desc = _clean_html_text(m.group(1))
            else:
                desc = f"Job listing with verified relocation and visa sponsorship for {card['title']} at {company}."
            time.sleep(1)  # Polite crawling
        except Exception as e:
            print(f"[Relocate.me] Detail fetch for {j_url} failed: {e}")
            desc = f"Relocation and visa sponsored role: {card['title']} at {company} in {card['location']}."

        jobs.append({
            "job_id": job_id,
            "title": card["title"],
            "company": company,
            "location": card["location"],
            "url": j_url,
            "description": desc,
            "search_keywords": f"relocate.me, {card['query']}",
        })

    print(f"[Relocate.me] Retrieved {len(jobs)} jobs with verified visa sponsorship.")
    return jobs


def scrape_all_international_sources(max_relocate_jobs: int = 25) -> List[Dict[str, Any]]:
    """Aggregate and save jobs from all dedicated international job platforms."""
    all_jobs: List[Dict[str, Any]] = []

    # 1. Arbeitnow (Germany & Europe English speaking jobs)
    try:
        an_jobs = scrape_arbeitnow(max_pages=2)
        all_jobs.extend(an_jobs)
    except Exception as e:
        print(f"[Arbeitnow] Scrape failed: {e}")

    # 2. Jobs4Internationals.de (Germany international talent portal)
    try:
        j4i_jobs = scrape_jobs4internationals()
        all_jobs.extend(j4i_jobs)
    except Exception as e:
        print(f"[Jobs4Internationals] Scrape failed: {e}")

    # 3. Relocate.me (Global relocation & visa sponsorship)
    try:
        rm_jobs = scrape_relocate_me(max_jobs=max_relocate_jobs)
        all_jobs.extend(rm_jobs)
    except Exception as e:
        print(f"[Relocate.me] Scrape failed: {e}")

    if all_jobs:
        save_jobs(all_jobs)
        print(f"Total {len(all_jobs)} international visa-friendly jobs ingested into jobs.db.")

    return all_jobs


if __name__ == "__main__":
    scrape_all_international_sources()
