import logging
import time
import sys
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus
import requests
import json
from pathlib import Path
import random
import inflect
import os
import re

from fastmcp import FastMCP
from pydantic import BaseModel
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import undetected_chromedriver as uc
from difflib import get_close_matches
# No direct environment variable access - using centralized settings approach

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.internal_mapping import INTERNAL_TO_INDEED_TITLES
from config.settings import settings
from utils.captcha_handler import handle_captcha_if_present
# ---------------- Logging ---------------- #
logger = logging.getLogger("mcp.scraping")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------------- MCP Init --------------- #
mcp_scraping = FastMCP("Scraping Server")


# --------------- Enhanced Driver Management ----------- #
class DriverManager:
    def __init__(self):
        self.driver = None
        self.retry_count = 0
        self.max_retries = 3
        
    def create_undetected_chrome_options(self, headless: bool = False, use_profile: bool = False) -> uc.ChromeOptions:
        """Create fresh undetected Chrome options - ALWAYS create new instance"""
        options = uc.ChromeOptions()
        
        # Basic stealth and stability options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-session-crashed-bubble")
        options.add_argument("--disable-restore-session-state")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        
        # Memory and performance
        options.add_argument("--memory-pressure-off")
        options.add_argument("--max_old_space_size=4096")
        options.add_argument("--incognito")  # Forces fresh non-cached, non-profiled session
        options.add_argument("--disable-site-isolation-trials")
        options.add_argument("--disable-features=InterestCohort,Topics,ThirdPartyStoragePartitioning")
        
        # User agent
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        # Profile and headless handling
        if use_profile:
            # Don't use headless with profile for extensions
            if headless:
                logger.warning("⚠️ Forcing non-headless mode for profile with extensions")
                headless = False
        elif headless:
            options.add_argument("--headless=new")
        else:
            # Fixed experimental options - proper format
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2,
                "profile.managed_default_content_settings.images": 1,
                "profile.default_content_settings.popups": 0
            })
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.cookies": 2,
                "profile.block_third_party_cookies": True,
                "profile.default_content_setting_values.popups": 0,
                "profile.managed_default_content_settings.images": 1,
                "profile.cookie_controls_mode": 2
            })
            
        return options
    
    def create_regular_chrome_options(self, headless: bool = False, use_profile: bool = False) -> Options:
        """Create regular Chrome options"""
        options = Options()
        
        # Basic options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        # User agent
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        # Profile and headless handling
        if use_profile:
            if headless:
                logger.warning("⚠️ Forcing non-headless mode for profile with extensions")
                headless = False
        elif headless:
            options.add_argument("--headless=new")
        else:
            # Experimental options
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2,
                "profile.managed_default_content_settings.images": 1
            })
        
        return options
    
    def get_driver(self, headless=False, use_profile=False):
        """Launch a basic Chrome browser with no profile, optionally headless"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        if headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(60)

        logger.info("🚀 New Chrome browser launched.")
        return self.driver

    def quit_driver(self):
        """Safely quit the driver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("🔚 Chrome driver closed successfully")
            except Exception as e:
                logger.warning(f"⚠️ Error closing driver: {e}")
            finally:
                self.driver = None

# --------------- Enhanced Job Scraper ----------- #
class JobScraper:
    def __init__(self):
        self.driver_manager = DriverManager()
    
    def extract_salary_from_text(self, text: str) -> str:
        if not text:
            return "Not specified"

        # Clean the text
        text = text.replace("\xa0", " ").replace("\n", " ").strip().lower()
        
        # Updated patterns with better regex
        salary_patterns = [
            # Range patterns: "$41.10 - $55.35 an hour", "$110,000 - $225,000 a year"
            r"\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*[-–—to]\s*\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s+(?:an hour|a year|per hour|per year|hourly|annually)",
            
            # Prefix patterns: "Up to $26 an hour", "Starting at $30 an hour", "From $28.50 an hour"
            r"(?:up to|starting at|from|starting|begins at)\s+\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s+(?:an hour|a year|per hour|per year|hourly|annually)",
            
            # Simple patterns: "$35.00 an hour", "$120,000 a year"
            r"\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s+(?:an hour|a year|per hour|per year|hourly|annually)",
            
            # Additional patterns for different formats
            r"\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*[-–—]\s*\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*/\s*(?:hr|hour|year|yr)",
            r"\$\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*/\s*(?:hr|hour|year|yr)",
        ]

        # Avoid known unrelated monetary keywords
        blacklist_keywords = ['401k', 'bonus', 'pto', 'vacation', 'commission', 'insurance', 'benefits']

        matches = []
        for pattern in salary_patterns:
            for match in re.finditer(pattern, text):
                full_match = match.group(0).strip()
                # Check if the match doesn't contain blacklisted keywords
                if not any(blk in full_match.lower() for blk in blacklist_keywords):
                    matches.append(full_match)

        # Deduplicate while preserving order
        seen = set()
        clean_salaries = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                clean_salaries.append(m)

        return " / ".join(clean_salaries) if clean_salaries else "Not specified"



    def extract_experience_from_text(self, text: str) -> str:
        if not text:
            return "Not specified"
        
        
        p = inflect.engine()

        text = text.replace("\xa0", " ").replace("\n", " ").strip().lower()
        sentences = re.split(r"[.!?\n;]", text)

        # Entry-level detection
        entry_patterns = [
            r'entry\s*level',
            r'no\s*experience\s*(required|necessary|needed)?',
            r'0\s*(years?|yrs?)',
            r'will\s*train',
            r'training\s*provided',
            r'new\s*graduate',
            r'recent\s*graduate',
        ]
        for sentence in sentences:
            for pat in entry_patterns:
                if re.search(pat, sentence):
                    return "Entry level / No experience required"

        # Map number words to digits (up to twenty)
        number_words = {
            word: str(p.number_to_words(word)) if isinstance(word, int) else str(num)
            for num, word in enumerate([
                'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
                'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
                'seventeen', 'eighteen', 'nineteen', 'twenty'
            ])
        }
        word_to_digit = {word: str(i) for i, word in enumerate(number_words)}

        # Replace number words in text (e.g. "two" => "2")
        def convert_number_words(t: str) -> str:
            return re.sub(r'\b(' + '|'.join(word_to_digit.keys()) + r')\b',
                        lambda m: word_to_digit[m.group(0)], t)

        converted_text = convert_number_words(text)
        converted_sentences = re.split(r"[.!?\n;]", converted_text)

        # Patterns (now working on numeric + converted word numbers)
        patterns = [
            (r"(\d+)\s*(?:to|–|-)\s*(\d+)\s*(?:years?|yrs?)", lambda m: f"{m.group(1)}-{m.group(2)} years experience"),
            (r"(\d+)\s*\+\s*(?:years?|yrs?)", lambda m: f"{m.group(1)}+ years experience"),
            (r"(?:at\s*least|min(?:imum)?|requires?|need(?:s)?|must\s*have)\s*(\d+)\s*(?:years?|yrs?)", lambda m: f"Minimum {m.group(1)} years experience"),
            (r"(\d+)\s*(?:years?|yrs?)\s*(?:experience|exp)?", lambda m: f"{m.group(1)} years experience"),
        ]

        for sentence in converted_sentences:
            sentence = sentence.strip().lower()
            for pat, formatter in patterns:
                match = re.search(pat, sentence)
                if match:
                    return formatter(match)

        return "Not specified"


    def extract_job_details(self, driver, job_element, index: int) -> Optional[Dict[str, Any]]:
        """Extract job details with improved salary extraction using CSS selectors first."""
        try:
            title = "Not specified"
            salary = "Not specified"
            experience = "Not specified"
            
            # ---------- TITLE ---------- #
            title_selectors = [
                "h2.jobTitle a span[title]",
                "h2.jobTitle a span",
                "h2.jobTitle span",
                "h2.jobTitle",
                "[data-testid='job-title']",
                ".jobTitle a",
                ".jobTitle"
            ]
            
            for selector in title_selectors:
                try:
                    title_elem = job_element.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_elem.get_attribute("title") or title_elem.text
                    if title_text and title_text.strip():
                        title = title_text.strip()
                        break
                except:
                    continue

            # ---------- ENHANCED SALARY EXTRACTION FROM CARD ---------- #
            # Try structured salary selectors first (like in your image)
            structured_salary_selectors = [
                ".css-1gznrtu .css-1ocltea",  # Based on your image
                ".css-1gznrtu span.css-1ocltea",
                ".css-1gznrtu [class*=]",
                ".salary-snippet-container .css-1ocltea",
                "[data-testid='salary-snippet'] .css-1ocltea",
                ".salarySnippet .css-1ocltea",
                ".estimated-salary .css-1ocltea",
                # More general selectors
                ".salary-snippet-container",
                "[data-testid='salary-snippet']",
                ".salarySnippet",
                ".estimated-salary",
                ".salary-snippet",
                ".salary",
                # Catch-all for any span with salary-like content
                "span[class*='salary']",
                "div[class*='salary']",
                "span[class*='pay']",
                "div[class*='pay']"
            ]
            
            for selector in structured_salary_selectors:
                try:
                    salary_elem = job_element.find_element(By.CSS_SELECTOR, selector)
                    salary_text = salary_elem.text.strip()
                    if salary_text and salary_text not in ["", "Not specified"]:
                        # Validate it's a proper salary format
                        if '$' in salary_text and not any(word in salary_text.lower() for word in ['401k', 'benefits', 'pto']):
                            salary = salary_text
                            logger.info(f"💰 Found salary in card with selector '{selector}': {salary}")
                            break
                except:
                    continue

            # ---------- GET JOB KEY AND OPEN DETAIL PAGE ---------- #
            job_key = None
            try:
                job_key_attrs = ["data-jk", "data-key", "id"]
                for attr in job_key_attrs:
                    try:
                        job_key = job_element.get_attribute(attr)
                        if job_key:
                            break
                    except:
                        continue
                        
                if not job_key:
                    try:
                        link_elem = job_element.find_element(By.CSS_SELECTOR, "h2.jobTitle a")
                        href = link_elem.get_attribute("href")
                        if href and "jk=" in href:
                            job_key = href.split("jk=")[1].split("&")[0]
                    except:
                        pass
                        
            except Exception as e:
                logger.warning(f"⚠️ Error getting job key for job {index}: {e}")

            # ---------- PROCESS DETAIL PAGE ---------- #
            if job_key:
                try:
                    job_url = f"{settings.indeed_base_url}/viewjob?jk={job_key}"
                    logger.info(f"🔍 Opening job detail page for job {index}: {job_url}")
                    
                    # Open in new tab
                    driver.execute_script("window.open(arguments[0]);", job_url)
                    driver.switch_to.window(driver.window_handles[-1])
                    
                    # Wait for page to load
                    WebDriverWait(driver, 15).until(
                        EC.any_of(
                            EC.presence_of_element_located((By.ID, "jobDescriptionText")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='job-description']")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".jobsearch-JobComponent-description")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".jobsearch-JobInfoHeader"))
                        )
                    )
                    
                    # ENHANCED SALARY EXTRACTION FROM JOB DETAIL PAGE
                    if salary == "Not specified":
                        # Try structured selectors from job detail page
                        detail_salary_selectors = [
                            # Specific salary container selectors
                            '.jobsearch-JobInfoHeader [data-testid="salary-snippet"]',
                            '.jobsearch-JobInfoHeader .css-1gznrtu .css-1ocltea',
                            '.jobsearch-JobInfoHeader span.css-1ocltea',
                            '.jobsearch-JobInfoHeader [class*=]',
                            '.jobsearch-JobInfoHeader .jobsearch-JobMetadataHeader-item',
                            '.jobsearch-JobInfoHeader .icl-u-xs-mr--xs',
                            # More general selectors
                            '[data-testid="salary-snippet"]',
                            '.css-1gznrtu .css-1ocltea',
                            'span.css-1oc7tea',
                            '.salary-snippet-container',
                            '.salarySnippet',
                            '.estimated-salary',
                            # Fallback selectors
                            'div[class*="salary"]',
                            'span[class*="salary"]',
                            'div[class*="pay"]',
                            'span[class*="pay"]'
                        ]
                        
                        for selector in detail_salary_selectors:
                            try:
                                salary_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                                for elem in salary_elems:
                                    salary_text = elem.text.strip()
                                    if salary_text and '$' in salary_text:
                                        # Validate it's actually salary info
                                        if any(term in salary_text.lower() for term in ['hour', 'year', 'annual', 'per']) or \
                                        re.search(r'\$\d+', salary_text):
                                            # Skip benefit-related items
                                            if not any(word in salary_text.lower() for word in ['401k', 'benefits', 'pto', 'vacation', 'insurance']):
                                                salary = salary_text
                                                logger.info(f"💰 Found salary in detail page with selector '{selector}': {salary}")
                                                break
                                if salary != "Not specified":
                                    break
                            except Exception as e:
                                logger.debug(f"Salary selector '{selector}' failed: {e}")
                                continue
                    
                    # Get job description text for experience extraction and regex salary fallback
                    full_text = ""
                    description_selectors = [
                        "#jobDescriptionText",
                        "[data-testid='job-description']",
                        ".jobsearch-JobComponent-description",
                        ".jobDescriptionContent"
                    ]
                    
                    for selector in description_selectors:
                        try:
                            desc_elem = driver.find_element(By.CSS_SELECTOR, selector)
                            full_text = desc_elem.text
                            if full_text:
                                break
                        except:
                            continue
                    
                    # Extract salary and experience from job description text (fallback)
                    if full_text:
                        # Only use regex extraction if CSS selectors didn't find anything
                        if salary == "Not specified":
                            extracted_salary = self.extract_salary_from_text(full_text)
                            if extracted_salary != "Not specified":
                                salary = extracted_salary
                                logger.info(f"💰 Extracted salary from text (regex fallback): {salary}")
                        
                        # Extract experience from job description
                        extracted_experience = self.extract_experience_from_text(full_text)
                        if extracted_experience != "Not specified":
                            experience = extracted_experience
                            logger.info(f"🎯 Extracted experience from text: {experience}")
                    
                    # Close the job detail tab
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    
                    # Small delay to avoid overwhelming the server
                    time.sleep(random.uniform(1, 2))
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error processing job detail page for job {index}: {e}")
                    # Make sure to close any open tabs and return to main window
                    try:
                        if len(driver.window_handles) > 1:
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                    except:
                        pass
            
            # Log the final extracted data
            logger.info(f"✅ [{index}] {title}")
            logger.info(f"    Salary: {salary}")
            logger.info(f"    Experience: {experience}")
            
            return {
                "job_title": title,
                "salary": salary,
                "experience": experience
            }

        except Exception as e:
            logger.error(f"❌ Failed to extract job {index}: {e}")
            return None

        
    def safe_navigate_to_indeed(self, driver, url: str, max_retries: int = 3) -> bool:
        """Safely navigate to Indeed with retries"""
        for attempt in range(max_retries):
            try:
                logger.info(f"🌐 Navigating to Indeed (attempt {attempt + 1}/{max_retries})...")
                
                driver.get("about:blank")
                time.sleep(2)
                driver.get(url)


                # ✅ Wait for the document to be ready
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )

                # ✅ Now it's safe to clear storage
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")

                
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") != "loading"
                )
                
                time.sleep(random.uniform(5, 8))
                
                current_url = driver.current_url.lower()
                page_source = driver.page_source.lower()
                
                if "indeed.com" in current_url:
                    logger.info(f"✅ Successfully navigated to Indeed: {current_url}")
                    return True
                elif any(keyword in page_source for keyword in ["captcha", "challenge", "blocked"]):
                    logger.warning("🧠 CAPTCHA detected, will handle separately")
                    return True
                else:
                    logger.warning(f"⚠️ Unexpected page loaded: {current_url}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    return False
                    
            except Exception as e:
                logger.warning(f"⚠️ Navigation attempt {attempt + 1} failed: {str(e)[:150]}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return False
        
        return False









    

    def scrape_jobs(self, job_title: str, location: str, max_results: int = 10) -> Dict[str, Any]:
        """Main scraping function with detailed job information extraction"""
        start_time = time.time()
        url = f"{settings.indeed_base_url}/jobs?q={quote_plus(job_title)}&l={quote_plus(location)}&sort=date"
        
        logger.info(f"🔍 Scraping jobs for '{job_title}' in '{location}'")
        logger.info(f"🌐 URL: {url}")
        
        jobs = []
        errors = []

        driver = self.driver_manager.get_driver(use_profile=True)
        if not driver:
            return {
                "success": False,
                "jobs": [],
                "errors": ["Failed to initialize Chrome driver with profile"],
                "total_scraped": 0,
                "scraping_time": round(time.time() - start_time, 2)
            }

        try:
            if not self.safe_navigate_to_indeed(driver, url):
                return {
                    "success": False,
                    "jobs": [],
                    "errors": ["Failed to navigate to Indeed after multiple attempts"],
                    "total_scraped": 0,
                    "scraping_time": round(time.time() - start_time, 2)
                }

            # Handle CAPTCHA if present
            if not handle_captcha_if_present(driver):
                logger.warning("⚠️ CAPTCHA handling failed, but continuing anyway...")
            else:
                logger.info("✅ CAPTCHA handled successfully or no CAPTCHA detected")

            logger.info("⏳ Waiting for job listings...")
            job_selectors = [
                ".job_seen_beacon",
                ".jobsearch-SerpJobCard", 
                "[data-jk]",
                ".slider_container .slider_item",
                ".result",
                "[data-testid='job-result']"
            ]

            job_elements = []
            for selector in job_selectors:
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_elements:
                        logger.info(f"✅ Found {len(job_elements)} job elements with selector: {selector}")
                        break
                except TimeoutException:
                    logger.warning(f"⚠️ Timeout waiting for selector: {selector}")
                    continue

            if not job_elements:
                logger.error("❌ No job elements found")
                return {
                    "success": False,
                    "jobs": [],
                    "errors": ["No job listings found on page"],
                    "total_scraped": 0,
                    "scraping_time": round(time.time() - start_time, 2)
                }

            # Determine allowed titles from mapping
            allowed_titles = set()
            if job_title in INTERNAL_TO_INDEED_TITLES:
                allowed_titles.update(INTERNAL_TO_INDEED_TITLES[job_title])
                allowed_titles.add(job_title)
            else:
                for key, aliases in INTERNAL_TO_INDEED_TITLES.items():
                    if job_title in aliases:
                        allowed_titles.update(aliases)
                        allowed_titles.add(key)
                        break
            if not allowed_titles:
                allowed_titles = {job_title}

            logger.info(f"📋 Searching for up to {max_results} matched jobs based on: {list(allowed_titles)}")

            i = 0
            matched_count = 0
            total_seen = 0

            while i < len(job_elements) and matched_count < max_results:
                job_element = job_elements[i]
                i += 1
                total_seen += 1

                try:
                    logger.info(f"🔍 Processing job {total_seen}/{len(job_elements)}")
                    job_data = self.extract_job_details(driver, job_element, total_seen)

                    if job_data:
                        title_cleaned = job_data["job_title"].strip().lower()

                        # Normalize allowed titles
                        allowed_cleaned = [alt.strip().lower() for alt in allowed_titles]

                        # 🔍 Log comparison inputs
                        logger.debug(f"🔍 Comparing: '{title_cleaned}' vs allowed titles: {allowed_cleaned}")

                        # ✅ Fuzzy match
                        match = get_close_matches(title_cleaned, allowed_cleaned, n=1, cutoff=0.7)

                        if match:
                            jobs.append(job_data)
                            matched_count += 1
                            logger.info(f"✅ Matched job #{matched_count}: {job_data['job_title']}")
                        else:
                            logger.info(f"❌ Skipped unrelated job: {job_data['job_title']}")

                    time.sleep(random.uniform(2, 4))

                except Exception as e:
                    error_msg = f"Error processing job {total_seen}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(f"⚠️ {error_msg}")

        except Exception as e:
            error_msg = f"Scraping error: {str(e)}"
            errors.append(error_msg)
            logger.error(f"❌ {error_msg}")

        finally:
            self.driver_manager.quit_driver()

        scraping_time = round(time.time() - start_time, 2)
        result = {
            "success": len(jobs) > 0,
            "jobs": jobs,
            "errors": errors,
            "total_scraped": len(jobs),
            "scraping_time": scraping_time
        }

        if jobs:
            logger.info(f"✅ Scraping completed successfully: {len(jobs)} jobs in {scraping_time}s")
        else:
            logger.warning(f"⚠️ Scraping completed with no results in {scraping_time}s")

        return result


# --------------- MCP Tools ----------- #
scraper = JobScraper()



@mcp_scraping.tool()
def scrape_jobs(job_title: str, location: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Scrape job listings from Indeed using internal title mapped to multiple common Indeed titles.
    Includes detailed salary and experience info.
    """
    start_time = time.time()
    mapped_titles = INTERNAL_TO_INDEED_TITLES.get(job_title, [job_title])

    all_jobs = []
    all_errors = []

    for title in mapped_titles:
        logger.info(f"🔁 Scraping for mapped title: '{title}'")
        result = scraper.scrape_jobs(title, location, max_results)
        
        for job in result.get("jobs", []):
            # job["mapped_from"] = job_title
            # job["searched_as"] = title
            all_jobs.append(job)
        
        all_errors.extend(result.get("errors", []))

    scraping_time = round(time.time() - start_time, 2)
    
    return {
        "success": bool(all_jobs),
        "jobs": all_jobs,
        "errors": all_errors,
        "total_scraped": len(all_jobs),
        "scraping_time": scraping_time
    }

@mcp_scraping.tool()
def health_check() -> Dict[str, Any]:
    """Health check for the scraping service"""
    logger.info("🏥 Running health check...")
    
    driver_manager = DriverManager()
    driver = driver_manager.get_driver(headless=True, use_profile=False)
    
    if not driver:
        return {"status": "unhealthy", "error": "Failed to initialize driver"}
    
    try:
        logger.info("🌐 Testing Indeed homepage...")
        driver.get(settings.indeed_base_url)
        
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        search_selectors = [
            'input[name="q"]',
            'input[id="text-input-what"]',
            '.jobsearch-SearchBox input'
        ]
        
        for selector in search_selectors:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"✅ Health check passed with selector: {selector}")
                return {"status": "healthy", "message": "Indeed homepage loaded successfully"}
            except TimeoutException:
                continue
        
        return {"status": "unhealthy", "error": "Could not find search elements on Indeed homepage"}
        
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
    finally:
        driver_manager.quit_driver()

# ---------------- Run Server ------------- #
if __name__ == "__main__":
    logger.info(f"🚀 Starting Enhanced Scraping MCP Server on port {settings.mcp_scraping_server_port}")
    mcp_scraping.run(transport="http", host=settings.mcp_server_bind_host, port=settings.mcp_scraping_server_port)