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
- Multi-level directory organization (--organize flag)

Usage:
    python download_skills.py <search_query> [min_stars]
    python download_skills.py --all [min_stars]    # Download all skills
    python download_skills.py --top N [min_stars]  # Download top N skills
    python download_skills.py --workers N          # Set number of parallel workers
    python download_skills.py --retry N            # Number of retries on failure
    python download_skills.py --organize           # Organize skills by category

Examples:
    python download_skills.py SEO 1000
    python download_skills.py --all 500 --workers 10
    python download_skills.py --top 100 --retry 3
    python download_skills.py --all --organize     # Organize by category
"""

import os
import sys
import requests
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re


class SkillCategorizer:
    """Categorizes skills based on their description using keyword matching."""
    
    # 分类规则：按照"功能/流程/权限"原则组织
    CATEGORIES = {
        # 功能分类 (Function)
        "Development": {
            "keywords": ["development", "coding", "programming", "dev", "build", "compile"],
            "subcategories": {
                "Frontend": ["frontend", "react", "vue", "angular", "UI", "web design", "css", "html"],
                "Backend": ["backend", "api", "server", "database", "sql", "postgresql", "redis"],
                "Mobile": ["mobile", "ios", "android", "react native", "flutter", "swift", "kotlin"],
                "DevOps": ["devops", "ci/cd", "docker", "kubernetes", "deployment", "infrastructure"]
            }
        },
        "Data": {
            "keywords": ["data", "analytics", "analysis", "machine learning", "ml", "ai"],
            "subcategories": {
                "DataScience": ["data science", "statistics", "visualization", "pandas", "numpy"],
                "MachineLearning": ["machine learning", "deep learning", "neural network", "pytorch", "tensorflow"],
                "DataEngineering": ["etl", "pipeline", "data warehouse", "spark", "airflow"]
            }
        },
        "Testing": {
            "keywords": ["test", "testing", "qa", "quality", "e2e", "unit test", "integration"],
            "subcategories": {
                "UnitTesting": ["unit test", "jest", "pytest", "vitest"],
                "E2ETesting": ["e2e", "end-to-end", "playwright", "cypress", "selenium"],
                "Performance": ["performance", "load test", "benchmark", "profiling"]
            }
        },
        "Documentation": {
            "keywords": ["documentation", "docs", "writing", "markdown", "readme"],
            "subcategories": {
                "Technical": ["technical writing", "api doc", "sdk doc"],
                "UserGuides": ["user guide", "tutorial", "how-to"],
                "Blog": ["blog", "article", "post"]
            }
        },
        "Security": {
            "keywords": ["security", "authentication", "authorization", "encryption", "compliance", "audit"],
            "subcategories": {
                "Auth": ["authentication", "oauth", "jwt", "sso"],
                "Audit": ["security audit", "vulnerability", "penetration test", "audit"],
                "Compliance": ["compliance", "gdpr", "hipaa", "pci", "regulatory"]
            }
        },
        "Design": {
            "keywords": ["design", "ui", "ux", "visual", "graphic"],
            "subcategories": {
                "UIDesign": ["ui design", "interface", "component library"],
                "UXDesign": ["ux design", "user experience", "usability"],
                "Graphics": ["graphics", "illustration", "image"]
            }
        },
        "Business": {
            "keywords": ["business", "product", "management", "strategy", "marketing"],
            "subcategories": {
                "ProductManagement": ["product", "prd", "roadmap", "feature"],
                "Marketing": ["marketing", "seo", "content", "social media"],
                "Analytics": ["analytics", "metrics", "kpi", "dashboard"]
            }
        },
        "Research": {
            "keywords": ["research", "scientific", "academic", "paper", "study"],
            "subcategories": {
                "Scientific": ["scientific", "biology", "chemistry", "physics"],
                "Academic": ["academic", "publication", "citation"],
                "Medical": ["medical", "healthcare", "clinical"]
            }
        }
    }
    
    @classmethod
    def categorize(cls, description: str) -> tuple[str, Optional[str]]:
        """
        Categorize a skill based on its description.
        
        Args:
            description: Skill description text
            
        Returns:
            Tuple of (category, subcategory)
        """
        if not description:
            return "Uncategorized", None
            
        desc_lower = description.lower()
        
        # Try to match subcategories first for better precision
        for category, config in cls.CATEGORIES.items():
            # Try to find subcategory first
            for subcat, subcat_keywords in config["subcategories"].items():
                if any(keyword in desc_lower for keyword in subcat_keywords):
                    return category, subcat
        
        # If no subcategory matched, try main category keywords
        for category, config in cls.CATEGORIES.items():
            if any(keyword in desc_lower for keyword in config["keywords"]):
                return category, None
        
        # No match found
        return "Uncategorized", None


class SkillsDownloader:
    API_BASE = "https://skillsmp.com/api/v1"
    AUTH_TOKEN = os.getenv("SKILLSMP_API_TOKEN", "sk_live_skillsmp_91-dUhDJ5m7NkJ_stVlNwsVucHnZ_lOHoG1OSoZAEUU")
    SKILLS_DIR = Path.home() / ".claude" / "skills"
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")  # Optional: GitHub token for API access

    def __init__(self, min_stars: int = 1000, workers: int = 5, max_retries: int = 3,
                 retry_delay: float = 1.0, organize: bool = False):
        self.min_stars = min_stars
        self.workers = workers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.organize = organize  # Enable multi-level organization
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
        if not self.SKILLS_DIR.exists():
            return
            
        if self.organize:
            # Search in organized directory structure
            for category_dir in self.SKILLS_DIR.iterdir():
                if not category_dir.is_dir():
                    continue
                # Check category and subcategory levels
                for item in category_dir.iterdir():
                    if item.is_dir():
                        if (item / "SKILL.md").exists():
                            self._downloaded_skills.add(item.name)
                        else:
                            # Check subcategory level
                            for skill_dir in item.iterdir():
                                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                                    self._downloaded_skills.add(skill_dir.name)
        else:
            # Flat directory structure
            for skill_dir in self.SKILLS_DIR.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    self._downloaded_skills.add(skill_dir.name)
                    
        if self._downloaded_skills:
            print(f"  ✓ Found {len(self._downloaded_skills)} existing skills")

    def get_skill_directory(self, skill: Dict) -> Path:
        """
        Get the target directory for a skill based on organization mode.
        
        Args:
            skill: Skill dictionary
            
        Returns:
            Path to skill directory
        """
        name = skill.get("name", "unknown")
        
        if not self.organize:
            # Flat structure: ~/.claude/skills/<skill-name>/
            return self.SKILLS_DIR / name
        
        # Multi-level structure: ~/.claude/skills/<category>/<subcategory>/<skill-name>/
        description = skill.get("description", "")
        category, subcategory = SkillCategorizer.categorize(description)
        
        if subcategory:
            return self.SKILLS_DIR / category / subcategory / name
        else:
            return self.SKILLS_DIR / category / name

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
        if self.organize:
            print("Organization mode: ENABLED (multi-level directory structure)")
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
        
        # Show category statistics if organizing
        if self.organize and all_skills:
            self._print_category_stats(all_skills)
            
        return all_skills

    def _print_category_stats(self, skills: List[Dict]):
        """Print categorization statistics."""
        category_counts = {}
        for skill in skills:
            description = skill.get("description", "")
            category, subcategory = SkillCategorizer.categorize(description)
            key = f"{category}/{subcategory}" if subcategory else category
            category_counts[key] = category_counts.get(key, 0) + 1
        
        print(f"\n{'='*60}")
        print("Category Distribution:")
        print(f"{'='*60}")
        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count} skills")

    def get_top_skills(self, n: int, min_stars: int = 0,
                       delay: float = 0.2) -> List[Dict]:
        """Get top N skills by stars."""
        all_skills = []
        page = 1
        limit = 50

        print(f"\n{'='*60}")
        print(f"Fetching TOP {n} skills (min_stars={min_stars})")
        if self.organize:
            print("Organization mode: ENABLED (multi-level directory structure)")
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

        # Show category statistics if organizing
        if self.organize and all_skills:
            self._print_category_stats(all_skills)

        return all_skills

    def filter_by_stars(self, skills: List[Dict]) -> List[Dict]:
        """Filter skills with star count >= min_stars."""
        filtered = [s for s in skills if s.get("stars", 0) >= self.min_stars]
        print(f"Found {len(filtered)} skills with >= {self.min_stars} stars")
        return filtered

    def parse_github_url(self, github_url: str) -> Optional[Dict[str, str]]:
        """Parse GitHub URL to extract owner, repo, branch, and path.
        
        Example:
        - Input: https://github.com/user/repo/tree/main/path/to/skill
        - Output: {
            "owner": "user",
            "repo": "repo", 
            "branch": "main",
            "path": "path/to/skill"
          }
        """
        if not github_url:
            return None
            
        # Remove trailing slash
        url = github_url.rstrip("/")
        
        # Pattern: https://github.com/{owner}/{repo}/tree/{branch}/{path}
        parts = url.replace("https://github.com/", "").split("/")
        
        if len(parts) < 4 or parts[2] != "tree":
            return None
            
        owner = parts[0]
        repo = parts[1]
        branch = parts[3]
        path = "/".join(parts[4:]) if len(parts) > 4 else ""
        
        return {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "path": path
        }
    
    def get_github_directory_contents(self, owner: str, repo: str, 
                                      path: str, branch: str = "main") -> List[Dict]:
        """Get directory contents from GitHub API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to directory
            branch: Branch name (default: main)
            
        Returns:
            List of file/directory info dictionaries
        """
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": branch}
        
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SkillsDownloader/1.0)"}
        if self.GITHUB_TOKEN:
            headers["Authorization"] = f"token {self.GITHUB_TOKEN}"
        
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # If API fails, try to get SKILL.md directly via raw URL
            print(f"    ⚠ GitHub API failed: {e}")
            return []
    
    def download_file_from_github(self, download_url: str, 
                                   output_path: Path) -> bool:
        """Download a single file from GitHub raw URL.
        
        Args:
            download_url: Raw file URL
            output_path: Local file path to save
            
        Returns:
            True if successful, False otherwise
        """
        github_session = requests.Session()
        github_session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SkillsDownloader/1.0)"
        })
        
        for attempt in range(self.max_retries):
            try:
                response = github_session.get(download_url, timeout=30)
                response.raise_for_status()
                
                # Create parent directory if needed
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write file
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                return True
                
            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    print(f"    ⚠ Retry {attempt + 1}/{self.max_retries} in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    print(f"    ✗ Failed to download: {e}")
                    return False
        
        return False
    
    def download_github_directory(self, owner: str, repo: str, 
                                   repo_path: str, local_path: Path,
                                   branch: str = "main") -> int:
        """Recursively download entire directory from GitHub.
        
        Args:
            owner: Repository owner
            repo: Repository name
            repo_path: Path in repository
            local_path: Local directory to save files
            branch: Branch name
            
        Returns:
            Number of files downloaded
        """
        contents = self.get_github_directory_contents(owner, repo, repo_path, branch)
        
        if not contents:
            return 0
        
        downloaded_count = 0
        
        for item in contents:
            item_type = item.get("type")
            item_name = item.get("name")
            item_path = item.get("path")
            
            if item_type == "file":
                # Download file
                download_url = item.get("download_url")
                if download_url:
                    output_file = local_path / item_name
                    if self.download_file_from_github(download_url, output_file):
                        print(f"    ✓ {item_name}")
                        downloaded_count += 1
                    
            elif item_type == "dir":
                # Recursively download subdirectory
                subdir_path = local_path / item_name
                subdir_count = self.download_github_directory(
                    owner, repo, item_path, subdir_path, branch
                )
                downloaded_count += subdir_count
        
        return downloaded_count

    def is_already_downloaded(self, skill: Dict) -> bool:
        """Check if a skill is already downloaded."""
        name = skill.get("name", "")
        return name in self._downloaded_skills

    def download_skill(self, skill: Dict, force: bool = False) -> bool:
        """Download a single skill file with retry logic.

        Args:
            skill: Skill dictionary
            force: Force re-download even if file exists

        Returns:
            True if download was successful, False otherwise
        """
        name = skill.get("name", "unknown")
        github_url = skill.get("githubUrl", "")
        
        if not github_url:
            print(f"  ⚠ No GitHub URL for {name}")
            return False

        # Parse GitHub URL
        url_info = self.parse_github_url(github_url)
        if not url_info:
            print(f"  ⚠ Invalid GitHub URL for {name}: {github_url}")
            return False

        # Get skill directory (flat or organized)
        skill_dir = self.get_skill_directory(skill)
        skill_md_path = skill_dir / "SKILL.md"

        # Check if already downloaded
        if skill_md_path.exists() and not force:
            if self.organize:
                description = skill.get("description", "")
                category, subcategory = SkillCategorizer.categorize(description)
                cat_path = f"{category}/{subcategory}" if subcategory else category
                print(f"  ✓ Already exists: {name} → {cat_path}")
            else:
                print(f"  ✓ Already exists: {name} → {skill_dir}")
            with self._lock:
                self._downloaded_skills.add(name)
            return True

        # Download entire directory from GitHub
        if self.organize:
            description = skill.get("description", "")
            category, subcategory = SkillCategorizer.categorize(description)
            cat_path = f"{category}/{subcategory}" if subcategory else category
            print(f"  📥 Downloading {name} → {cat_path}...")
        else:
            print(f"  📥 Downloading {name}...")
        
        try:
            downloaded_count = self.download_github_directory(
                owner=url_info["owner"],
                repo=url_info["repo"],
                repo_path=url_info["path"],
                local_path=skill_dir,
                branch=url_info["branch"]
            )
            
            # If directory download failed, try downloading SKILL.md directly
            if downloaded_count == 0 or not skill_md_path.exists():
                print(f"    ⚠ Directory download failed, trying direct SKILL.md download...")
                if self.download_skill_md_directly(url_info, skill_dir):
                    downloaded_count = 1
            
            if downloaded_count > 0 and skill_md_path.exists():
                stars = skill.get("stars", 0)
                print(f"  ✓ Downloaded {name} ({downloaded_count} files, {stars} stars)")
                
                with self._lock:
                    self._downloaded_skills.add(name)
                return True
            else:
                print(f"  ✗ Failed to download {name} - SKILL.md not found")
                # Clean up empty directory
                if skill_dir.exists() and not any(skill_dir.iterdir()):
                    skill_dir.rmdir()
                return False
                
        except Exception as e:
            print(f"  ✗ Error downloading {name}: {e}")
            # Clean up partial download
            if skill_dir.exists() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()
            return False
    
    def download_skill_md_directly(self, url_info: Dict[str, str], 
                                    skill_dir: Path) -> bool:
        """Fallback: Download SKILL.md directly via raw URL.
        
        Args:
            url_info: Parsed GitHub URL info
            skill_dir: Local skill directory
            
        Returns:
            True if successful, False otherwise
        """
        owner = url_info["owner"]
        repo = url_info["repo"]
        branch = url_info["branch"]
        path = url_info["path"]
        
        # Try both SKILL.md and skill.md
        for filename in ["SKILL.md", "skill.md"]:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}/{filename}"
            output_path = skill_dir / "SKILL.md"
            
            if self.download_file_from_github(raw_url, output_path):
                return True
        
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
        if self.organize:
            print(f"Skills directory: {self.SKILLS_DIR} (organized by category)")
        else:
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
        if self.organize:
            print(f"Organization: Multi-level directory structure enabled")
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
    organize = False

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
        elif arg == "--organize":
            organize = True
            i += 1
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
        "n": n,
        "organize": organize
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    params = parse_args()

    downloader = SkillsDownloader(
        min_stars=params["min_stars"],
        workers=params["workers"],
        max_retries=params["max_retries"],
        organize=params["organize"]
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
