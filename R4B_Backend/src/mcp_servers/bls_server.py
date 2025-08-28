import requests
from bs4 import BeautifulSoup
import time
from rapidfuzz import process, fuzz
import re
import os
import sys
from urllib.parse import urljoin, urlparse
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastmcp import FastMCP
import asyncio
from datetime import datetime, timedelta
import json

# Import centralized settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import settings

# ------------------------- Logging ------------------------- #
logger = logging.getLogger("mcp.bls_scraper")
logging.basicConfig(level=logging.INFO)

# ------------------------- MCP Init ------------------------ #
mcp = FastMCP("BLS Job Search Server")

# ------------------------- Constants ------------------------ #
BASE_URL = "https://www.bls.gov"
OOH_BASE_URL = f"{BASE_URL}/ooh"

# Common abbreviation patterns for dynamic expansion
COMMON_ABBREVIATIONS = {
    # Technical roles
    r'\bit\b': ['information technology', 'tech', 'computer'],
    r'\bai\b': ['artificial intelligence', 'machine learning'],
    r'\bml\b': ['machine learning', 'artificial intelligence'],
    r'\bqa\b': ['quality assurance', 'testing'],
    r'\bqc\b': ['quality control', 'inspection'],
    
    # Business roles
    r'\bhr\b': ['human resources', 'personnel'],
    r'\bceo\b': ['chief executive officer', 'executive'],
    r'\bcfo\b': ['chief financial officer', 'finance'],
    r'\bcto\b': ['chief technology officer', 'technology'],
    
    # Healthcare
    r'\brn\b': ['registered nurse', 'nursing'],
    r'\blpn\b': ['licensed practical nurse', 'nursing'],
    r'\bemr\b': ['electronic medical records', 'health records'],
    
    # Technical trades
    r'\bhvac\b': ['heating', 'air conditioning', 'refrigeration', 'climate', 'ventilation'],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# -------------------- Pydantic Models ---------------------- #
class JobSearchResponse(BaseModel):
    success: bool
    job_title: Optional[str] = None
    url: Optional[str] = None
    group: Optional[str] = None
    group_title: Optional[str] = None
    median_pay: Optional[str] = None
    match_score: Optional[int] = None
    message: str = ""
    alternatives: List[str] = []

class JobIndexStatus(BaseModel):
    total_jobs: int
    total_groups: int
    last_updated: Optional[str] = None
    status: str = "unknown"

# -------------------- Global State ----------------------- #
class JobIndexCache:
    def __init__(self):
        self.job_index = []
        self.last_updated = None
        self.update_interval = timedelta(hours=24)  # Refresh every 24 hours
    
    def needs_update(self) -> bool:
        if not self.job_index or not self.last_updated:
            return True
        return datetime.now() - self.last_updated > self.update_interval
    
    def update_index(self, new_index: List[Dict]):
        self.job_index = new_index
        self.last_updated = datetime.now()
    
    def get_index(self) -> List[Dict]:
        return self.job_index

# Global cache instance
job_cache = JobIndexCache()

# -------------------- Core Functions ---------------------- #
def discover_group_pages():
    """Dynamically discover all occupation group pages from the main OOH page"""
    print("🔍 Discovering occupation groups from BLS website...")
    
    try:
        # First, try the main OOH page
        main_url = f"{OOH_BASE_URL}/home.htm"
        resp = requests.get(main_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        group_pages = []
        
        # Method 1: Look for links that follow the pattern /ooh/[group]/home.htm
        links = soup.find_all("a", href=True)
        
        for link in links:
            href = link.get("href", "")
            title = link.get_text(strip=True)
            
            # Match pattern like "/ooh/computer-and-information-technology/home.htm"
            if (href.startswith("/ooh/") and 
                href.endswith("/home.htm") and 
                href != "/ooh/home.htm" and  # Exclude the main page
                href.count("/") == 3):  # Should be /ooh/group/home.htm
                
                group_name = href.split("/")[2]  # Extract group name
                group_pages.append({
                    "name": group_name,
                    "title": title,
                    "url": BASE_URL + href
                })
                print(f"  ✅ Found group: {title} ({group_name})")
        
        # Method 2: If Method 1 doesn't work, try looking for occupation group containers
        if not group_pages:
            print("🔄 Trying alternative discovery method...")
            
            # Look for common containers that might hold group links
            containers = soup.find_all(["div", "section", "ul"], class_=re.compile(r"group|occupation|category", re.I))
            
            for container in containers:
                links = container.find_all("a", href=True)
                for link in links:
                    href = link.get("href", "")
                    title = link.get_text(strip=True)
                    
                    if ("/ooh/" in href and 
                        "home.htm" in href and 
                        href != "/ooh/home.htm" and
                        len(title) > 5):  # Reasonable title length
                        
                        # Make sure it's a full URL
                        full_url = urljoin(BASE_URL, href)
                        group_name = href.split("/ooh/")[-1].replace("/home.htm", "")
                        
                        if group_name and group_name not in [g["name"] for g in group_pages]:
                            group_pages.append({
                                "name": group_name,
                                "title": title,
                                "url": full_url
                            })
                            print(f"  ✅ Found group: {title} ({group_name})")
        
        # Method 3: Fallback - try to construct URLs based on common patterns
        if not group_pages:
            print("🔄 Using fallback method with common occupation group patterns...")
            common_groups = [
                "architecture-and-engineering",
                "arts-and-design", 
                "building-and-grounds-cleaning-and-maintenance",
                "business-and-financial",
                "community-and-social-service",
                "computer-and-information-technology",
                "construction-and-extraction",
                "education-training-and-library",
                "healthcare",
                "management"
            ]
            
            for group in common_groups:
                test_url = f"{OOH_BASE_URL}/{group}/home.htm"
                try:
                    test_resp = requests.head(test_url, headers=HEADERS, timeout=10)
                    if test_resp.status_code == 200:
                        group_pages.append({
                            "name": group,
                            "title": group.replace("-", " ").title(),
                            "url": test_url
                        })
                        print(f"  ✅ Verified group: {group}")
                except:
                    pass
        
        print(f"✅ Discovered {len(group_pages)} occupation groups")
        return group_pages
        
    except Exception as e:
        print(f"⚠️ Failed to discover groups: {e}")
        return []

def fetch_job_index():
    """Build job index from dynamically discovered group pages"""
    print("📦 Building job index from discovered group pages...")
    
    group_pages = discover_group_pages()
    if not group_pages:
        print("❌ No group pages discovered!")
        return []
    
    job_index = []
    
    for group_info in group_pages:
        group_name = group_info["name"]
        group_url = group_info["url"]
        print(f"🔍 Fetching jobs from: {group_info['title']}")
        
        try:
            resp = requests.get(group_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Look for job links in various containers
            links = soup.find_all("a", href=True)
            
            for link in links:
                href = link.get("href", "")
                title = link.get_text(strip=True)
                
                # Filter for actual job pages
                if (href.startswith(f"/ooh/{group_name}/") and 
                    href.endswith(".htm") and 
                    href != f"/ooh/{group_name}/home.htm" and
                    title and
                    len(title) > 3 and
                    not any(skip in title.lower() for skip in ["image", "back to", "home", "print"])):
                    
                    full_url = BASE_URL + href
                    job_index.append({
                        "title": title, 
                        "url": full_url, 
                        "group": group_name,
                        "group_title": group_info["title"]
                    })
                    print(f"  ✅ Found: {title}")
            
        except Exception as e:
            print(f"⚠️ Failed to fetch {group_name}: {e}")
        
        time.sleep(0.5)  # Be respectful with delays
    
    print(f"✅ Total jobs indexed: {len(job_index)}")
    return job_index
    


def generate_query_variants(query, job_titles):
    variants = [query.lower()]
    
    for abbrev_pattern, expansions in COMMON_ABBREVIATIONS.items():
        if re.search(abbrev_pattern, query, re.IGNORECASE):
            for expansion in expansions:
                expanded = re.sub(abbrev_pattern, expansion, query, flags=re.IGNORECASE)
                if expanded.lower() not in variants:
                    variants.append(expanded.lower())

    query_words = set(query.lower().split())

    for title in job_titles:
        title_words = set(title.lower().split())
        if query_words.issubset(title_words) and len(title_words) > len(query_words):
            if title.lower() not in variants:
                variants.append(title.lower())

    word_synonyms = {
        'tech': ['technician', 'technology', 'technical'],
        'dev': ['developer', 'development'],
        'eng': ['engineer', 'engineering'],
        'mgr': ['manager', 'management'],
        'admin': ['administrator', 'administrative'],
        'spec': ['specialist', 'specialist'],
        'assist': ['assistant', 'aide'],
        'coord': ['coordinator'],
        'rep': ['representative'],
        'sales': ['salesperson', 'sales representative']
    }

    for short_form, long_forms in word_synonyms.items():
        if short_form in query.lower():
            for long_form in long_forms:
                expanded = query.lower().replace(short_form, long_form)
                if expanded not in variants:
                    variants.append(expanded)

    if any(word in query.lower() for word in ['computer', 'software', 'data', 'web']):
        tech_variants = [
            query.lower() + ' analyst',
            query.lower() + ' specialist',
            query.lower() + ' engineer',
            'computer ' + query.lower()
        ]
        variants.extend([v for v in tech_variants if v not in variants])

    if any(word in query.lower() for word in ['medical', 'health', 'care']):
        health_variants = [
            query.lower() + ' technician',
            query.lower() + ' aide',
            'healthcare ' + query.lower()
        ]
        variants.extend([v for v in health_variants if v not in variants])

    return variants[:10]


def find_best_match(job_index, query):
    if not job_index:
        return None

    choices = [job["title"] for job in job_index]
    query_variants = generate_query_variants(query, choices)

    print(f"🔄 Trying {len(query_variants)} query variants:")
    for variant in query_variants[:5]:
        print(f"  • {variant}")

    domain_keywords = {
        'hvac': ['hvac', 'heating', 'air conditioning', 'refrigeration', 'climate', 'ventilation'],
        'automotive': ['automotive', 'vehicle', 'car', 'truck', 'auto', 'diesel'],
        'computer': ['computer', 'software', 'information technology', 'data', 'programming'],
        'medical': ['medical', 'health', 'nurse', 'doctor', 'healthcare', 'clinical'],
        'electrical': ['electrical', 'electrician', 'power', 'wiring']
    }

    query_lower = query.lower()
    detected_domain = None
    for domain, keywords in domain_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_domain = domain
            break

    # ✅ Direct domain keyword fallback (no hardcoded titles)
    if detected_domain:
        keywords = domain_keywords[detected_domain]
        for job in job_index:
            title_lower = job['title'].lower()
            matched_keywords = [kw for kw in keywords if kw in title_lower]
            if len(matched_keywords) >= 3:
                print(f"🎯 Strong {detected_domain.upper()} match via keywords in title: {job['title']}")
                return job

    # Proceed with fuzzy matching
    best_result = None
    best_score = 0
    used_variant = query

    for variant in query_variants:
        try:
            all_results = process.extract(variant, choices, scorer=fuzz.WRatio, limit=10)

            if detected_domain:
                domain_keywords_set = domain_keywords[detected_domain]
                domain_matches = []
                other_matches = []

                for match_title, score, idx in all_results:
                    match_lower = match_title.lower()
                    has_domain_keywords = any(keyword in match_lower for keyword in domain_keywords_set)

                    if has_domain_keywords:
                        domain_matches.append((match_title, score, idx))
                    else:
                        other_matches.append((match_title, score, idx))

                if domain_matches:
                    print(f"🎯 Found {len(domain_matches)} {detected_domain.upper()} domain matches:")
                    for match_title, score, _ in domain_matches[:3]:
                        print(f"  • {match_title} ({score:.1f}%)")

                    best_domain_match = domain_matches[0]
                    if other_matches:
                        best_other_match = other_matches[0]
                        if best_other_match[1] > best_domain_match[1] + 15:
                            candidate = best_other_match
                        else:
                            candidate = best_domain_match
                    else:
                        candidate = best_domain_match
                else:
                    candidate = all_results[0] if all_results else None
            else:
                candidate = all_results[0] if all_results else None

            if candidate and candidate[1] > best_score:
                best_result = candidate
                best_score = candidate[1]
                used_variant = variant

        except Exception as e:
            print(f"⚠️ Error processing variant '{variant}': {e}")
            continue

    if best_result is None:
        return None

    best_match, score, idx = best_result

    if used_variant != query:
        print(f"🎯 Best match using variant: '{used_variant}'")

    print(f"🎯 Match score: {score}% for '{best_match}'")

    # Enforce minimum score threshold
    min_score = 60
    if detected_domain:
        match_lower = best_match.lower()
        domain_keywords_set = domain_keywords[detected_domain]
        is_domain_match = any(keyword in match_lower for keyword in domain_keywords_set)

        if not is_domain_match:
            min_score = 85
            print(f"⚠️ Cross-domain match detected. Requiring {min_score}% minimum score.")

    if score < min_score:
        print(f"❌ Score {score:.1f}% below minimum threshold of {min_score}%")
        print("🔍 Other potential matches:")
        all_results = process.extract(used_variant, choices, scorer=fuzz.WRatio, limit=5)
        for match, match_score, _ in all_results[:3]:
            if match != best_match:
                match_lower = match.lower()
                domain_indicator = ""
                if detected_domain:
                    if any(keyword in match_lower for keyword in domain_keywords[detected_domain]):
                        domain_indicator = f" [{detected_domain.upper()}]"
                print(f"  • {match} ({match_score:.1f}%){domain_indicator}")
        return None

    return job_index[idx]




def extract_median_pay(url):
    try:
        print(f"💰 Extracting pay from: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True).lower()
                    if "median pay" in cell_text or "median annual wage" in cell_text:
                        if i + 1 < len(cells):
                            pay_text = cells[i + 1].get_text(strip=True)
                            if "$" in pay_text:
                                return pay_text
                        elif "$" in cell.get_text():
                            return cell.get_text(strip=True)

        content_divs = soup.find_all(["div", "section", "p"])
        for div in content_divs:
            text = div.get_text()
            pay_patterns = [
                r"Median pay[:\s]+\$[\d,]+(?:\s+(?:per year|annually))?",
                r"median annual wage[^$]*\$[\d,]+",
                r"Median annual wage[:\s]+\$[\d,]+"
            ]

            for pattern in pay_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(0).strip()

        salary_match = re.search(r"\$[\d,]+(?:\s+(?:per year|annually|annual))?", soup.get_text())
        if salary_match:
            return salary_match.group(0).strip()

        return None
        
    except Exception as e:
        print(f"⚠️ Failed to fetch pay info: {e}")
        return None

def search_and_display(query, job_index):
    print(f"\n{'='*50}")
    print(f"🔍 SEARCHING: {query.upper()}")
    print('='*50)
    
    match = find_best_match(job_index, query)
    if not match:
        print("❌ No good match found.")
        # Show some similar jobs
        if job_index:
            print("\n💡 Available jobs include:")
            for job in job_index:
                if "heating" in job["title"].lower():
                    print(f"🔥 Matchable job in index: {job['title']}")

        return

    print(f"✅ Best match: {match['title']}")
    print(f"📂 Group: {match.get('group_title', match['group'])}")
    print(f"🌐 URL: {match['url']}")

    pay = extract_median_pay(match['url'])
    if pay:
        print(f"💰 Pay Info: {pay}")
    else:
        print("❌ Pay information not found.")

# ---------------------- MCP Tools -------------------------- #

@mcp.tool()
def search_job(job_title: str) -> Dict[str, Any]:
    """Search for a job by title in the BLS Occupational Outlook Handbook"""
    logger.info(f"🔍 Searching for job: {job_title}")
    
    try:
        # Ensure we have a current job index
        if job_cache.needs_update():
            logger.info("🔄 Updating job index...")
            new_index = fetch_job_index()
            job_cache.update_index(new_index)
        
        job_index = job_cache.get_index()
        
        if not job_index:
            return JobSearchResponse(
                success=False,
                message="Job index is empty. Please check BLS website accessibility."
            ).dict()
        
        # Find best match - now returns just the match object like test file
        match = find_best_match(job_index, job_title)

        if not match:
            # Get alternatives for failed matches
            choices = [job["title"] for job in job_index]
            try:
                alternatives_results = process.extract(job_title, choices, scorer=fuzz.WRatio, limit=5)
                alternatives = [result[0] for result in alternatives_results if result[1] > 40]
            except:
                alternatives = []
                
            return JobSearchResponse(
                success=False,
                message="No good match found for the job title",
                alternatives=alternatives[:5]
            ).dict()
        
        # Extract pay information
        median_pay = extract_median_pay(match['url'])
        
        response = JobSearchResponse(
            success=True,
            job_title=match['title'],
            url=match['url'],
            group=match['group'],
            group_title=match.get('group_title', match['group']),
            median_pay=median_pay,
            message=f"Found job: {match['title']}"
        )
        
        logger.info(f"✅ Found job: {match['title']} with pay: {median_pay or 'N/A'}")
        return response.dict()
        
    except Exception as e:
        logger.error(f"❌ Error searching for job: {e}")
        return JobSearchResponse(
            success=False,
            message=f"Error occurred during search: {str(e)}"
        ).dict()



@mcp.tool()
def health_check() -> Dict[str, Any]:
    """Check server health and job index status"""
    job_index = job_cache.get_index()
    
    return {
        "status": "healthy" if job_index else "degraded",
        "job_index_size": len(job_index),
        "last_updated": job_cache.last_updated.isoformat() if job_cache.last_updated else None,
        "needs_update": job_cache.needs_update(),
        "server": "BLS Job Search Server"
    }



# ------------------- Run Server ---------------------------- #
if __name__ == "__main__":
    logger.info(f"🚀 Starting BLS Job Search MCP Server on port {settings.mcp_bls_server_port} (HTTP)")
    
    # Initialize job index on startup
    try:
        logger.info("📦 Initializing job index...")
        initial_index = fetch_job_index()
        job_cache.update_index(initial_index)
        logger.info(f"✅ Initial job index loaded with {len(initial_index)} jobs")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize job index: {e}")
    
    mcp.run(transport="http", host=settings.mcp_server_bind_host, port=settings.mcp_bls_server_port)