#!/usr/bin/env python3
"""Pipeline Runner: End-to-end autonomous job scraper, scorer, tailor, and Slack notifier.

Replaces n8n completely:
1. Scrapes LinkedIn across target regions (guest/anonymous mode).
2. Scores discovered jobs deterministically (0-10) against profile.json.
3. Queries unapplied shortlisted jobs (score >= 7.0).
4. Generates tailored ATS LaTeX resume & cover letter PDFs with Gemini + Tectonic.
5. Uploads Slack notifications with the tailored resume PDF attached directly.
"""

import argparse
import sys
import time
from pathlib import Path

# Add scraper root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db import (
    get_connection,
    get_shortlist,
    get_unfiltered_jobs,
    init_db,
    update_filter_result,
)
from app.filters import apply_filters, load_profile
from app.generator import tailor_documents_for_job
from app.slack_notifier import send_slack_notification


def run_pipeline(
    max_details: int = 25,
    min_score: float = 7.0,
    skip_scrape: bool = False,
    skip_generate: bool = False,
    skip_slack: bool = False,
):
    print("=" * 70)
    print("🚀 STARTING AUTONOMOUS JOB PIPELINE")
    print("=" * 70)
    init_db()

    # ----------------------------------------------------
    # Phase 1: Scraping Jobs (LinkedIn + Dedicated International Boards)
    # ----------------------------------------------------
    if not skip_scrape:
        print("\n[Phase 1a/4] Scraping LinkedIn across target regions (guest incognito)...")
        try:
            from app.scraper import scrape_jobs
            scraped = scrape_jobs(max_details=max_details, headless=True)
            print(f"Scraped {len(scraped)} jobs successfully from LinkedIn.")
        except Exception as e:
            print(f"Warning: LinkedIn scrape encountered an error: {e}")

        print("\n[Phase 1b/4] Scraping dedicated international visa-sponsorship boards...")
        try:
            from app.international_scrapers import scrape_all_international_sources
            intl_scraped = scrape_all_international_sources()
            print(f"Scraped {len(intl_scraped)} jobs from international visa platforms.")
        except Exception as e:
            print(f"Warning: International scrapers encountered an error: {e}")
    else:
        print("\n[Phase 1/4] Skipping scrapers as requested.")

    # ----------------------------------------------------
    # Phase 2: Deterministic 0-10 Scoring & Filtering
    # ----------------------------------------------------
    print("\n[Phase 2/4] Scoring unfiltered jobs against profile.json...")
    unfiltered = get_unfiltered_jobs()
    profile = load_profile()
    scored_count = 0
    passed_count = 0

    for job in unfiltered:
        result = apply_filters(job, profile=profile)
        update_filter_result(job["job_id"], result)
        scored_count += 1
        if result.status == "passed" and result.score >= min_score:
            passed_count += 1

    print(f"Evaluated {scored_count} new jobs ({passed_count} newly passed score >= {min_score}).")

    # ----------------------------------------------------
    # Phase 3: Fetch Unapplied Shortlisted Jobs
    # ----------------------------------------------------
    print(f"\n[Phase 3/4] Fetching unapplied shortlist (min_score >= {min_score})...")
    shortlist_jobs = get_shortlist(min_score=min_score, only_unapplied=True)
    print(f"Found {len(shortlist_jobs)} unapplied shortlisted jobs needing attention.")

    if not shortlist_jobs:
        print("No pending jobs to tailor or notify. Pipeline complete.")
        return

    # ----------------------------------------------------
    # Phase 4: Document Tailoring & Slack Notifications
    # ----------------------------------------------------
    print("\n[Phase 4/4] Tailoring documents and sending Slack notifications...")
    success_count = 0

    for idx, job in enumerate(shortlist_jobs, start=1):
        job_id = job["job_id"]
        title = job.get("title", "Role")
        company = job.get("company", "Company")
        score = job.get("score", "N/A")

        print(f"\n[{idx}/{len(shortlist_jobs)}] Job {job_id}: {title} @ {company} (Score: {score})")

        resume_pdf_path = None
        cover_letter_pdf_path = None

        if not skip_generate:
            try:
                gen_result = tailor_documents_for_job(job_id)
                resume_pdf_path = Path(gen_result["resume_pdf"])
                cover_letter_pdf_path = Path(gen_result["cover_letter_pdf"])
                cached_str = " (from cache)" if gen_result.get("cached") else " (tailored fresh)"
                print(f"  PDF ready{cached_str}: {resume_pdf_path.name}")
            except Exception as e:
                print(f"  Generation failed for {job_id}: {e}")

        if not skip_slack:
            try:
                sent = send_slack_notification(
                    job=job,
                    resume_pdf_path=resume_pdf_path,
                    cover_letter_pdf_path=cover_letter_pdf_path,
                )
                if sent:
                    success_count += 1
                time.sleep(2)  # Space out Slack notifications cleanly
            except Exception as e:
                print(f"  Slack notification failed for {job_id}: {e}")

    print("\n" + "=" * 70)
    print(f"🎉 PIPELINE COMPLETED: {success_count}/{len(shortlist_jobs)} jobs processed and alerted.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run autonomous job search, tailoring, and alert pipeline.")
    parser.add_argument("--max-details", type=int, default=25, help="Max job details to scrape (default: 25)")
    parser.add_argument("--min-score", type=float, default=7.0, help="Minimum match score threshold (default: 7.0)")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip LinkedIn scraping phase")
    parser.add_argument("--skip-generate", action="store_true", help="Skip Gemini tailoring phase")
    parser.add_argument("--skip-slack", action="store_true", help="Skip sending Slack messages")

    args = parser.parse_args()
    run_pipeline(
        max_details=args.max_details,
        min_score=args.min_score,
        skip_scrape=args.skip_scrape,
        skip_generate=args.skip_generate,
        skip_slack=args.skip_slack,
    )


if __name__ == "__main__":
    main()
