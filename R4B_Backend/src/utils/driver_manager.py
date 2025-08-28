"""
Selenium WebDriver management utilities for job scraping.
"""

import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
import undetected_chromedriver as uc

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.logging_config import get_logger
from utils.error_handlers import ScrapingError, retry_on_failure, log_execution_time

logger = get_logger(__name__)

class DriverManager:
    """Manages Selenium WebDriver instances with proper configuration and cleanup."""
    
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
                "profile.managed_default_content_settings.images": 1,
                "profile.default_content_settings.popups": 0
            })
        
        return options
    
    @retry_on_failure(max_retries=3, delay=2.0)
    @log_execution_time
    def get_driver(self, headless=False, use_profile=False, use_undetected=True):
        """Get a configured WebDriver instance."""
        try:
            if use_undetected:
                options = self.create_undetected_chrome_options(headless, use_profile)
                driver = uc.Chrome(options=options)
            else:
                options = self.create_regular_chrome_options(headless, use_profile)
                driver = webdriver.Chrome(options=options)
            
            # Set page load timeout
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(10)
            
            self.driver = driver
            logger.info("✅ WebDriver initialized successfully")
            return driver
            
        except WebDriverException as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise ScrapingError(f"Driver initialization failed: {str(e)}", error_code="DRIVER_INIT_ERROR")
        except Exception as e:
            logger.error(f"Unexpected error during driver initialization: {e}")
            raise ScrapingError(f"Unexpected driver error: {str(e)}", error_code="DRIVER_ERROR")
    
    def quit_driver(self):
        """Safely quit the WebDriver instance."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ WebDriver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.quit_driver()


