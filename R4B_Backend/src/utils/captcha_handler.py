"""
CAPTCHA handling utilities for job scraping.
"""

import logging
import time
import random
import re
import os
import sys
import requests
from typing import Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Import settings instead of direct .env access
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import settings

logger = logging.getLogger(__name__)


def find_turnstile_iframe(driver) -> Optional[str]:
    """Find Turnstile iframe and extract sitekey."""
    try:
        # Try to detect iframe and extract sitekey
        found = False
        sitekey = None
        
        for attempt in range(10):  # 10 retries = ~30s
            human_interaction(driver)
            iframes_css = driver.find_elements(By.CSS_SELECTOR,
                "iframe[src*='challenges.cloudflare.com/cdn-cgi/challenge-platform']")
            iframes_xpath = driver.find_elements(
                By.XPATH, "/html/body/main/div/div/div[1]/div/div//iframe")
            all_iframes = iframes_css + iframes_xpath

            for iframe in all_iframes:
                src = iframe.get_attribute("src")
                if src and "0x" in src:
                    match = re.search(r'/((0x[a-zA-Z0-9]+))', src)
                    if match:
                        sitekey = match.group(1)
                        logger.info(f"✅ Found sitekey: {sitekey}")
                        found = True
                        break
            if found:
                break

            logger.info("Waiting for Turnstile iframe to appear...")
            time.sleep(3)
            
        return sitekey
    except Exception as e:
        logger.error(f"Error finding Turnstile iframe: {e}")
        return None


def has_real_captcha(driver) -> bool:
    """Detect if Turnstile CAPTCHA is present."""
    try:
        page_source = driver.page_source.lower()
        soup = BeautifulSoup(page_source, "html.parser")

        # ✅ Check for Turnstile iframe (Cloudflare pattern)
        for iframe in soup.find_all("iframe", src=True):
            if "challenges.cloudflare.com/cdn-cgi/challenge-platform" in iframe["src"]:
                logger.info("🔍 Found Turnstile iframe.")
                return True

        # ✅ Check for Turnstile widget div (for non-Cloudflare usage)
        if soup.find("div", {"class": "cf-turnstile"}) or soup.find("div", {"data-sitekey": True}):
            logger.info("🔍 Found Turnstile widget div.")
            return True

        # ✅ Check fallback indicators
        fallback_indicators = [
            "verify you are human",
            "cf-turnstile",
            "security check",
        ]
        for indicator in fallback_indicators:
            if indicator in page_source:
                logger.info(f"🔍 Found CAPTCHA hint text: {indicator}")
                return True

        return False
    except Exception as e:
        logger.warning(f"⚠️ CAPTCHA detection failed: {e}")
        return False


def human_interaction(driver):
    """Trigger human-like page interaction."""
    try:
        driver.execute_script("window.scrollTo(0, 400);")
        driver.execute_script("window.scrollBy(0, 100);")
        driver.execute_script("document.body.click();")
        time.sleep(random.uniform(0.5, 1.2))
    except Exception:
        pass


def solve_with_2captcha(sitekey: str, page_url: str, max_wait: int = 120) -> Optional[str]:
    """Solve CAPTCHA using 2captcha service."""
    try:
        api_key = settings.apikey_2captcha
        if not api_key:
            logger.error("❌ APIKEY_2CAPTCHA environment variable not set")
            return None

        # ✅ Submit to 2Captcha
        logger.info("🧠 Sending task to 2Captcha...")
        submit_url = (
            f"{settings.captcha_2captcha_submit_url}?key={api_key}"
            f"&method=turnstile"
            f"&sitekey={sitekey}"
            f"&pageurl={page_url}"
            f"&json=1")
        response = requests.get(submit_url).json()
        if response.get("status") != 1:
            logger.error(f"❌ 2Captcha task submission failed: {response}")
            return None

        captcha_id = response["request"]

        # ⏳ Poll until solution is ready
        solution = None
        fetch_url = f"{settings.captcha_2captcha_result_url}?key={api_key}&action=get&id={captcha_id}&json=1"
        logger.info(f"⏳ Waiting for 2Captcha solution (job ID: {captcha_id})...")
        for i in range(max_wait // 5):
            time.sleep(5)
            poll = requests.get(fetch_url).json()
            if poll.get("status") == 1:
                solution = poll["request"]
                logger.info("✅ CAPTCHA solved.")
                break
            logger.info("...still waiting for 2Captcha result.")
        else:
            logger.error("❌ CAPTCHA not solved within allowed time.")
            return None

        return solution
    except Exception as e:
        logger.error(f"❌ Exception during 2Captcha solving: {e}")
        return None


def inject_captcha_token(driver, solution: str) -> bool:
    """Inject CAPTCHA token into page."""
    try:
        logger.info("⚡ Injecting CAPTCHA token into page...")
        injection_js = f"""
        const token = "{solution}";
        let inputs = [
        "input[name='cf-turnstile-response']",
        "input[name='cf_challenge_response']",
        "input[id$='_response']"
        ];
        inputs.forEach(sel => {{
            let el = document.querySelector(sel);
            if (el) {{
                el.value = token;
                el.style.display = "block";
            }}
        }});
        """
        driver.execute_script(injection_js)
        time.sleep(1)

        # ✅ Try submitting form or clicking submit
        try:
            driver.find_element(By.TAG_NAME, "form").submit()
        except Exception:
            try:
                driver.find_element(By.CSS_SELECTOR,
                    "button[type='submit'],input[type='submit']").click()
            except Exception:
                pass

        # Wait until CAPTCHA disappears
        logger.info("⏳ Waiting for CAPTCHA element to be removed...")
        WebDriverWait(driver, 30).until(
            lambda d: "cf-turnstile" not in d.page_source.lower()
        )
        logger.info("✅ CAPTCHA successfully bypassed.")
        return True
    except Exception as e:
        logger.error(f"❌ Error injecting CAPTCHA token: {e}")
        return False


def wait_for_captcha_resolution(driver, max_wait: int = 120) -> bool:
    """Wait for CAPTCHA resolution using 2captcha."""
    try:
        sitekey = None
        page_url = driver.current_url
        fallback_sitekey = None  # No hardcoded fallback - must detect from page
        debug_prefix = "turnstile_debug"

        logger.warning("🧠 CAPTCHA detected. Solving Turnstile challenge with 2Captcha...")

        # Try to detect iframe and extract sitekey
        sitekey = find_turnstile_iframe(driver)

        # Use fallback sitekey if necessary
        if not sitekey:
            sitekey = fallback_sitekey
            if not sitekey or not sitekey.startswith("0x"):
                logger.error("❌ Could not extract or fallback to valid sitekey.")
                return False
            logger.warning(f"⚠️ Falling back to hardcoded sitekey: {sitekey}")

        # Solve with 2captcha
        solution = solve_with_2captcha(sitekey, page_url, max_wait)
        if not solution:
            return False

        # Inject token
        return inject_captcha_token(driver, solution)

    except Exception as e:
        logger.error(f"❌ Exception during CAPTCHA solving: {e}")
        try:
            driver.save_screenshot(f"{debug_prefix}_error.png")
            with open(f"{debug_prefix}_error.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            logger.error("⚠️ Failed to save debug output.")
        return False


def handle_captcha_if_present(driver) -> bool:
    """Handle CAPTCHA if present on the page."""
    try:
        if has_real_captcha(driver):
            return wait_for_captcha_resolution(driver)
        return True
    except Exception as e:
        logger.error(f"Error handling CAPTCHA: {e}")
        return False
