#!/usr/bin/env python3
"""
Download Claude skills from SkillsMP marketplace.

This script searches for skills matching a query, filters by star count,
and downloads them to ~/.claude/skills directory.

Features:
- Parallel downloads with configurable workers
- Automatic retry on failures
- Resume capability (skip already downloaded skills)
- Support for both skill.md and SKILL.md file names

Usage:
    python download_skills.py <search_query> [min_stars]
    python download_skills.py --all [min_stars]    # Download all skills
    python download_skills.py --top N [min_stars]  # Download top N skills
    python download_skills.py --workers N          # Set number of parallel workers
    python download_skills.py --retry N            # Number of retries on failure

Examples:
    python download_skills.py SEO 1000
    python download_skills.py --all 500 --workers 10
    python download_skills.py --top 100 --retry 3
"""

import os
import sys
import requests
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class SkillsDownloader:
    API_BASE = "https://skillsmp.com/api/v1"
    AUTH_TOKEN = "sk_live_skillsmp_91-dUhDJ5m7NkJ_stVlNwsVucHnZ_lOHoG1OSoZAEUU"
    SKILLS_DIR = Path.home() / ".claude" / "skills"

    def __init__(self, min_stars: int = 1000, workers: int = 5, max_retries: int = 3,
                 retry_delay: float = 1.0):
        self.min_stars = min_stars
        self.workers = workers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.AUTH_TOKEN}",
            "User-Agent": "Mozilla/5.0 (compatible; SkillsDownloader/1.0)"
        })

        # Track downloaded skills for thread safety
        self._downloaded_skills: Set[str] = set()
        self._lock = threading.Lock()

        # Load already downloaded skills
        self._load_downloaded_skills()

    def _load_downloaded_skills(self):
        """Load already downloaded skills from the skills directory."""
        if self.SKILLS_DIR.exists():
            for f in self.SKILLS_DIR.glob("*.md"):
                skill_id = f.stem
                self._downloaded_skills.add(skill_id)
            print(f"  ✓ Found {len(self._downloaded_skills)} existing skills")

    def search_skills(self, query: str, page: int = 1, limit: int = 50,
                      sort_by: str = "stars", order: str = "desc") -> List[Dict]:
        """Search for skills matching the query with pagination."""
        url = f"{self.API_BASE}/skills/search"
        params = {
            "q": query,
            "page": page,
            "limit": limit,
            "sortBy": sort_by,
            "order": order
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                print(f"API returned unsuccessful response: {data}")
                return [], {}

            skills = data.get("data", {}).get("skills", [])
            pagination = data.get("data", {}).get("pagination", {})
            return skills, pagination

        except requests.RequestException as e:
            print(f"Error searching skills: {e}")
            return [], {}

    def get_all_skills(self, min_stars: Optional[int] = None,
                       max_skills: Optional[int] = None,
                       delay: float = 0.3) -> List[Dict]:
        """Download all skills from the marketplace using pagination."""
        min_stars = min_stars if min_stars is not None else self.min_stars
        all_skills = []
        page = 1
        limit = 50
        total_downloaded = 0

        print(f"\n{'='*60}")
        print(f"Fetching ALL skills (min_stars={min_stars})")
        print(f"{'='*60}\n")

        while True:
            skills, pagination = self.search_skills(
                query="a",
                page=page,
                limit=limit,
                sort_by="stars",
                order="desc"
            )

            if not skills:
                break

            if min_stars > 0:
                skills = [s for s in skills if s.get("stars", 0) >= min_stars]

            all_skills.extend(skills)
            total_downloaded += len(skills)

            print(f"Page {page}: fetched {len(skills)} skills "
                  f"(total: {total_downloaded})")

            if max_skills and total_downloaded >= max_skills:
                all_skills = all_skills[:max_skills]
                break

            has_next = pagination.get("hasNext", False)
            if not has_next:
                break

            page += 1
            time.sleep(delay)

        print(f"\nTotal skills fetched: {len(all_skills)}")
        return all_skills

    def get_top_skills(self, n: int, min_stars: int = 0,
                       delay: float = 0.2) -> List[Dict]:
        """Get top N skills by stars."""
        all_skills = []
        page = 1
        limit = 50

        print(f"\n{'='*60}")
        print(f"Fetching TOP {n} skills (min_stars={min_stars})")
        print(f"{'='*60}\n")

        while len(all_skills) < n:
            skills, pagination = self.search_skills(
                query="a",
                page=page,
                limit=limit,
                sort_by="stars",
                order="desc"
            )

            if not skills:
                break

            all_skills.extend(skills)

            print(f"Page {page}: fetched {len(skills)} skills "
                  f"(total: {len(all_skills)})")

            if len(all_skills) >= n:
                all_skills = all_skills[:n]
                break

            has_next = pagination.get("hasNext", False)
            if not has_next:
                break

            page += 1
            time.sleep(delay)

        if min_stars > 0:
            all_skills = [s for s in all_skills if s.get("stars", 0) >= min_stars]
            print(f"\nAfter min_stars filter: {len(all_skills)} skills")

        return all_skills

    def filter_by_stars(self, skills: List[Dict]) -> List[Dict]:
        """Filter skills with star count >= min_stars."""
        filtered = [s for s in skills if s.get("stars", 0) >= self.min_stars]
        print(f"Found {len(filtered)} skills with >= {self.min_stars} stars")
        return filtered

    def get_skill_download_urls(self, skill: Dict) -> List[str]:
        """Convert githubUrl to raw content URL.

        Returns a list of possible URLs (tries both skill.md and SKILL.md).

        Example conversion:
        - From: https://github.com/user/repo/tree/main/path/to/skill
        - To: https://raw.githubusercontent.com/user/repo/main/path/to/skill/skill.md
        """
        github_url = skill.get("githubUrl", "")

        if not github_url:
            return []

        # Replace github.com with raw.githubusercontent.com
        url = github_url.replace("github.com", "raw.githubusercontent.com")
        # Replace /tree/ with / to get the raw content path
        url = url.replace("/tree/", "/")
        url = url.rstrip("/")

        # Try both skill.md (lowercase) and SKILL.md (uppercase)
        urls = [
            f"{url}/skill.md",
            f"{url}/SKILL.md"
        ]

        return urls

    def is_already_downloaded(self, skill: Dict) -> bool:
        """Check if a skill is already downloaded."""
        skill_id = skill.get("id", "")
        return skill_id in self._downloaded_skills

    def download_skill(self, skill: Dict, force: bool = False) -> bool:
        """Download a single skill file with retry logic.

        Args:
            skill: Skill dictionary
            force: Force re-download even if file exists

        Returns:
            True if download was successful, False otherwise
        """
        name = skill.get("name", "unknown")
        skill_id = skill.get("id", "unknown")
        download_urls = self.get_skill_download_urls(skill)

        if not download_urls:
            print(f"  ⚠ No download URL for {name}")
            return False

        output_path = self.SKILLS_DIR / f"{skill_id}.md"

        # Check if already downloaded
        if output_path.exists() and not force:
            print(f"  ✓ Already exists: {name} → {output_path}")
            with self._lock:
                self._downloaded_skills.add(skill_id)
            return True

        # Create a separate session for GitHub downloads (without Auth token)
        github_session = requests.Session()
        github_session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SkillsDownloader/1.0)"
        })

        # Try each URL
        for download_url in download_urls:
            # Retry loop for each URL
            for attempt in range(self.max_retries):
                try:
                    response = github_session.get(download_url, timeout=30)
                    response.raise_for_status()

                    # HTML response indicates file doesn't exist at this URL
                    if response.text.strip().startswith("<!DOCTYPE html>"):
                        continue  # Try next URL

                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(response.text)

                    stars = skill.get("stars", 0)
                    print(f"  ✓ Downloaded {name} ({stars} stars) → {output_path}")

                    with self._lock:
                        self._downloaded_skills.add(skill_id)
                    return True

                except requests.RequestException as e:
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (attempt + 1)
                        print(f"  ⚠ Retry {attempt + 1}/{self.max_retries} for {name} "
                              f"in {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        # Try next URL if available
                        continue

        # All URLs failed
        print(f"  ✗ Failed to download {name} - all URLs failed")
        return False

    def download_skills_parallel(self, skills: List[Dict],
                                 force: bool = False) -> tuple:
        """Download multiple skills in parallel.

        Args:
            skills: List of skill dictionaries to download
            force: Force re-download even if files exist

        Returns:
            Tuple of (success_count, total_count)
        """
        # Filter out already downloaded skills
        skills_to_download = []
        skipped = 0

        for skill in skills:
            if self.is_already_downloaded(skill) and not force:
                skipped += 1
            else:
                skills_to_download.append(skill)

        if skipped > 0:
            print(f"\nSkipped {skipped} already downloaded skills")

        if not skills_to_download:
            print("\nNo new skills to download.")
            return 0, len(skills)

        print(f"\n{'='*60}")
        print(f"Downloading {len(skills_to_download)} skills "
              f"(with {self.workers} parallel workers):")
        print(f"{'='*60}")

        success_count = 0
        total_count = len(skills_to_download)

        # Use ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            # Submit all download tasks
            future_to_skill = {
                executor.submit(self.download_skill, skill, force): skill
                for skill in skills_to_download
            }

            # Process completed tasks
            for future in as_completed(future_to_skill):
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    skill = future_to_skill[future]
                    name = skill.get("name", "unknown")
                    print(f"  ✗ Unexpected error downloading {name}: {e}")

        return success_count, total_count

    def ensure_skills_dir(self):
        """Ensure the skills directory exists."""
        self.SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Skills directory: {self.SKILLS_DIR}")

    def run_search(self, query: str):
        """Run a search-based download."""
        print(f"\n{'='*60}")
        print(f"Searching for skills matching: {query}")
        print(f"Minimum stars: {self.min_stars}")
        print(f"{'='*60}\n")

        self.ensure_skills_dir()

        skills, pagination = self.search_skills(query)
        if not skills:
            print("No skills found. Exiting.")
            return

        print(f"\n{'='*60}")
        print("All skills found:")
        print(f"{'='*60}")
        for skill in skills:
            stars = skill.get("stars", 0)
            name = skill.get("name", "unknown")
            author = skill.get("author", "unknown")
            print(f"  • {name} by {author} - {stars} stars")

        filtered_skills = self.filter_by_stars(skills)
        if not filtered_skills:
            print(f"\nNo skills with >= {self.min_stars} stars found.")
            return

        success, total = self.download_skills_parallel(filtered_skills)
        self._print_summary(success, total)

    def run_all(self, min_stars: Optional[int] = None):
        """Download all skills."""
        min_stars = min_stars if min_stars is not None else self.min_stars
        self.ensure_skills_dir()

        skills = self.get_all_skills(min_stars=min_stars)
        if not skills:
            print("No skills found.")
            return

        success, total = self.download_skills_parallel(skills)
        self._print_summary(success, total)

    def run_top(self, n: int, min_stars: Optional[int] = None):
        """Download top N skills."""
        min_stars = min_stars if min_stars is not None else self.min_stars
        self.ensure_skills_dir()

        skills = self.get_top_skills(n, min_stars=min_stars)
        if not skills:
            print("No skills found.")
            return

        success, total = self.download_skills_parallel(skills)
        self._print_summary(success, total)

    def _print_summary(self, success: int, total: int):
        """Print download summary."""
        print(f"\n{'='*60}")
        print(f"Download complete: {success}/{total} skills")
        print(f"Already downloaded: {len(self._downloaded_skills)} skills total")
        print(f"{'='*60}")


def parse_args():
    """Parse command line arguments."""
    args = sys.argv[1:]

    # Default values
    query = None
    min_stars = 1000
    workers = 5
    max_retries = 3
    mode = None
    n = None

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--all":
            mode = "all"
            i += 1
        elif arg == "--top":
            mode = "top"
            if i + 1 < len(args):
                n = int(args[i + 1])
                i += 2
            else:
                print("Error: --top requires a number argument")
                sys.exit(1)
        elif arg == "--workers":
            if i + 1 < len(args):
                workers = int(args[i + 1])
                i += 2
            else:
                print("Error: --workers requires a number argument")
                sys.exit(1)
        elif arg == "--retry":
            if i + 1 < len(args):
                max_retries = int(args[i + 1])
                i += 2
            else:
                print("Error: --retry requires a number argument")
                sys.exit(1)
        elif arg.startswith("-"):
            print(f"Unknown option: {arg}")
            sys.exit(1)
        else:
            # This is the search query
            query = arg
            min_stars = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 0
            i += 1

    return {
        "query": query,
        "min_stars": min_stars,
        "workers": workers,
        "max_retries": max_retries,
        "mode": mode,
        "n": n
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    params = parse_args()

    downloader = SkillsDownloader(
        min_stars=params["min_stars"],
        workers=params["workers"],
        max_retries=params["max_retries"]
    )

    if params["mode"] == "all":
        downloader.run_all(min_stars=params["min_stars"])
    elif params["mode"] == "top":
        if params["n"] is None:
            print("Error: --top requires a number argument")
            sys.exit(1)
        downloader.run_top(params["n"], min_stars=params["min_stars"])
    elif params["query"]:
        downloader.run_search(params["query"])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
