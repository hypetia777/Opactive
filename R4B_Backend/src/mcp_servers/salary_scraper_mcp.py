import logging
import time
import sys
import os
from typing import Dict, Any, Optional, List
import csv
import json
import random
from pathlib import Path

from fastmcp import FastMCP
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc

# Import settings instead of direct .env access
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import settings

# ---------------- Logging ---------------- #
logger = logging.getLogger("mcp.salary_scraping")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------------- MCP Init --------------- #
mcp_salary = FastMCP("Salary.com Scraping Server")

# ---------------- Config ---------------- #
USERNAME = settings.salary_com_username or "demo_user@example.com"
PASSWORD = settings.salary_com_password or "CHANGE_ME_PASSWORD"
LOGIN_URL = settings.salary_com_login_url

# ---------------- Driver Management ---------------- #
class DriverManager:
    def __init__(self):
        self.driver = None
        
    def get_driver(self, headless=False):
        """Launch Chrome browser with optimized settings"""
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        if headless:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")
            
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(60)
        
        logger.info("Chrome browser launched for Salary.com scraping")
        return self.driver
    
    def quit_driver(self):
        """Safely quit the driver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome driver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")
            finally:
                self.driver = None

# ---------------- Salary.com Scraper ---------------- #
class SalaryComScraper:
    def __init__(self):
        self.driver_manager = DriverManager()
    
    def login(self, driver) -> bool:
        """Login to Salary.com"""
        try:
            logger.info("Navigating to Salary.com login page...")
            driver.get(LOGIN_URL)
            time.sleep(5)

            # Switch to iframe for login if needed
            found = False
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                driver.switch_to.frame(iframe)
                if "loginid" in driver.page_source:
                    found = True
                    break
            if not found:
                driver.switch_to.default_content()

            # Login
            logger.info("Entering credentials...")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "loginid"))
            ).send_keys(USERNAME)
            driver.find_element(By.ID, "password").send_keys(PASSWORD)
            driver.find_element(By.XPATH, "//button[contains(text(), 'Sign In')]").click()

            # Handle "Continue to CompAnalyst" popup
            try:
                WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.ID, "continueUseOld"))
                ).click()
                time.sleep(1)
                logger.info("Clicked 'Continue to CompAnalyst'")
            except:
                logger.info("No 'Continue to CompAnalyst' modal found")
                pass

            logger.info("Successfully logged in to Salary.com")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def navigate_to_market_data(self, driver) -> bool:
        """Navigate to CompAnalyst Market Data"""
        try:
            logger.info("Navigating to Market Data...")
            WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Market Data"))
            ).click()
            time.sleep(2)
            driver.find_element(By.LINK_TEXT, "CompAnalyst Market Data").click()
            logger.info("Successfully navigated to Market Data")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to Market Data: {e}")
            return False
    
    def search_job_title(self, driver, job_title: str) -> bool:
        """Search for job title"""
        try:
            logger.info(f"Searching for job title: {job_title}")
            search_input = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'input[type="search"][placeholder="Search..."]')
                )
            )
            search_input.clear()
            search_input.send_keys(job_title)
            search_input.send_keys(Keys.RETURN)
            time.sleep(2)
            logger.info(f"Searched for: {job_title}")
            return True
        except Exception as e:
            logger.error(f"Failed to search job title: {e}")
            return False
    
    def select_first_job(self, driver) -> bool:
        """Select the first job from search results"""
        try:
            logger.info("Selecting first job from results...")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            
            first_row = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            checkbox_label = first_row.find_element(By.CSS_SELECTOR, "label.sa-table-checkbox")
            driver.execute_script("arguments[0].click();", checkbox_label)
            time.sleep(1)

            # Verify selection
            if "sa-table-row-selected" not in first_row.get_attribute("class"):
                raise Exception("Row not selected!")
            
            logger.info("Successfully selected first job")
            return True
        except Exception as e:
            logger.error(f"Failed to select first job: {e}")
            return False
    
    def proceed_to_scope(self, driver) -> bool:
        """Click 'Next: Scope' button"""
        try:
            logger.info("Proceeding to Scope section...")
            next_scope_btn = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.btn.sa-wizard-btn-next'))
            )
            driver.execute_script("arguments[0].click();", next_scope_btn)
            time.sleep(2)
            logger.info("Moved to Scope section")
            return True
        except Exception as e:
            logger.error(f"Failed to proceed to scope: {e}")
            return False
    
    def click_new_scope(self, driver) -> bool:
        """Click 'New Scope' button"""
        try:
            logger.info("Clicking 'New Scope' button...")
            try:
                new_scope_btn = WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[span[@class="icon-add"] and contains(text(),"New Scope")]'))
                )
                driver.execute_script("arguments[0].click();", new_scope_btn)
                time.sleep(3)
                logger.info("New Scope button clicked")
                return True
            except Exception as e:
                logger.warning(f"Primary selector failed: {e}")
                # Try alternative selectors
                alternative_selectors = [
                    '//a[contains(text(),"New Scope")]',
                    '//button[contains(text(),"New Scope")]',
                    '//*[contains(text(),"New Scope")]',
                    '//a[contains(@class,"btn") and contains(text(),"Scope")]'
                ]
                
                for selector in alternative_selectors:
                    try:
                        new_scope_btn = driver.find_element(By.XPATH, selector)
                        if new_scope_btn.is_displayed() and new_scope_btn.is_enabled():
                            logger.info(f"Found New Scope with alternative selector: {selector}")
                            driver.execute_script("arguments[0].click();", new_scope_btn)
                            time.sleep(3)
                            return True
                    except:
                        continue
                
                logger.error("Could not find New Scope button with any selector")
                return False
                
        except Exception as e:
            logger.error(f"Failed to click New Scope: {e}")
            return False
    
    def configure_geography(self, driver, city: str) -> bool:
        """Configure geography settings"""
        try:
            logger.info(f"Configuring geography for: {city}")
            
            # Wait for modal
            modal_selectors = [
                'div[role="dialog"]', '.modal-content', '.modal', 
                '.sa-addscope-add', '#addScopeModal', 'div[aria-modal="true"]'
            ]
            
            modal = None
            for selector in modal_selectors:
                try:
                    modal = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Modal found with selector: {selector}")
                    break
                except:
                    continue
            
            if not modal:
                logger.error("Could not find modal")
                return False

            # Ensure GEOGRAPHY section is expanded
            try:
                geo_section = driver.find_element(By.ID, "sa-addscope-geography")
                if "collapse in" not in geo_section.get_attribute("class"):
                    geo_toggle = driver.find_element(By.CSS_SELECTOR, 'a[href="#sa-addscope-geography"]')
                    driver.execute_script("arguments[0].click();", geo_toggle)
                    time.sleep(2)
                    logger.info("Geography section expanded")
            except Exception as e:
                logger.warning(f"Geography section handling: {e}")

            # Find city search input
            city_search = None
            selectors_to_try = [
                'input[placeholder="Search Metro, City, Zip..."]',
                '#geography-search input',
                '.sa-addscope-geography-container input[type="text"]',
                'input.form-control[placeholder*="Metro"]',
                '#geo_container input'
            ]
            
            for selector in selectors_to_try:
                try:
                    city_search = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"City search input found with selector: {selector}")
                    break
                except:
                    continue
            
            if not city_search:
                logger.error("Could not find city search input")
                return False

            # Search for the city
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", city_search)
            time.sleep(1)
            city_search.clear()
            time.sleep(0.5)
            city_search.send_keys(city)
            time.sleep(2)
            logger.info(f"{city} entered in search field")

            # Select first city checkbox
            logger.info(f"Selecting first {city} checkbox...")
            city_selected = False
            
            try:
                first_city_checkbox = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[@id="tab_searchResult"]//input[@type="checkbox"][1]'))
                )
                driver.execute_script("arguments[0].click();", first_city_checkbox)
                city_selected = True
                logger.info(f"First {city} checkbox selected")
            except Exception as e:
                logger.warning(f"Primary approach failed: {e}")
                try:
                    city_checkboxes = driver.find_elements(By.XPATH, '//ul[@class="ul-top1"]//input[@type="checkbox"]')
                    if city_checkboxes and len(city_checkboxes) > 0:
                        first_checkbox = city_checkboxes[0]
                        driver.execute_script("arguments[0].click();", first_checkbox)
                        city_selected = True
                        logger.info(f"First {city} checkbox selected via fallback")
                except Exception as e2:
                    logger.warning(f"Fallback approach also failed: {e2}")
            
            if not city_selected:
                logger.error(f"Could not select any {city} option")
                return False
            
            time.sleep(1)
            logger.info("Geography configuration completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure geography: {e}")
            return False
    
    def configure_industry(self, driver) -> bool:
        """Configure industry settings"""
        try:
            logger.info("Configuring industry settings...")
            
            # Expand Industry section
            try:
                industry_toggle = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href="#sa-addscope-industry"]'))
                )
                
                industry_section = driver.find_element(By.ID, "sa-addscope-industry")
                if "in" not in industry_section.get_attribute("class"):
                    logger.info("Industry section is collapsed, expanding...")
                    driver.execute_script("arguments[0].click();", industry_toggle)
                    time.sleep(1)
                else:
                    logger.info("Industry section is already expanded")
                    
            except Exception as e:
                logger.warning(f"Error expanding Industry section: {e}")

            # Select "All Industries" checkbox
            logger.info("Selecting All Industries...")
            try:
                all_industries_checkbox = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//li[@id="industry_I00"]//input[@type="checkbox"]'))
                )
                
                if not all_industries_checkbox.is_selected():
                    driver.execute_script("arguments[0].click();", all_industries_checkbox)
                    logger.info("All Industries selected")
                else:
                    logger.info("All Industries already selected")
                    
            except Exception as e:
                logger.warning(f"Primary All Industries selection failed: {e}")
                try:
                    all_industries_checkbox = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, '//label[contains(.,"All Industries")]/input[@type="checkbox"]'))
                    )
                    if not all_industries_checkbox.is_selected():
                        driver.execute_script("arguments[0].click();", all_industries_checkbox)
                        logger.info("All Industries selected via fallback")
                except Exception as e2:
                    logger.warning(f"Both All Industries approaches failed: {e2}")

            time.sleep(1)

            # Collapse Industry section before expanding Company Size
            logger.info("Collapsing Industry section...")
            try:
                industry_toggle = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href="#sa-addscope-industry"]'))
                )
                industry_section = driver.find_element(By.ID, "sa-addscope-industry")
                if "in" in industry_section.get_attribute("class"):
                    driver.execute_script("arguments[0].click();", industry_toggle)
                    time.sleep(1)
                    logger.info("Industry section collapsed")
            except Exception as e:
                logger.warning(f"Error collapsing Industry section: {e}")
            
            logger.info("Industry configuration completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure industry: {e}")
            return False
    
    def configure_company_size(self, driver) -> bool:
        """Configure company size settings"""
        try:
            logger.info("Configuring company size...")
            
            # Expand Company Size section
            logger.info("Expanding Company Size section...")
            try:
                company_size_toggle = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href="#sa-addscope-companysize"]'))
                )
                company_size_section = driver.find_element(By.ID, "sa-addscope-companysize")
                if "in" not in company_size_section.get_attribute("class"):
                    driver.execute_script("arguments[0].click();", company_size_toggle)
                    time.sleep(1)
                    logger.info("Company Size section expanded")
                else:
                    logger.info("Company Size section already expanded")
            except Exception as e:
                logger.warning(f"Error expanding Company Size section: {e}")

            # Select "50 - 100 FTEs" checkbox
            logger.info("Selecting 50 - 100 FTEs...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.ID, "sa-addscope-companysize"))
                )
                
                selectors_50_100 = [
                    '//label[contains(.,"50 - 100 FTEs")]/input[@type="checkbox"]',
                    '//input[@type="checkbox" and @value="50 - 100 FTEs"]',
                    '//li[contains(.,"50 - 100 FTEs")]//input[@type="checkbox"]',
                    '//div[@id="sa-addscope-companysize"]//label[contains(.,"50 - 100")]//input[@type="checkbox"]'
                ]
                
                fte_selected = False
                for selector in selectors_50_100:
                    try:
                        fte_checkbox = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        if not fte_checkbox.is_selected():
                            driver.execute_script("arguments[0].click();", fte_checkbox)
                            logger.info(f"50 - 100 FTEs selected using selector: {selector}")
                        else:
                            logger.info("50 - 100 FTEs already selected")
                        fte_selected = True
                        break
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue
                
                if not fte_selected:
                    logger.error("Could not select 50 - 100 FTEs with any selector")
                    return False
                    
            except Exception as e:
                logger.error(f"Error selecting 50 - 100 FTEs: {e}")
                return False

            time.sleep(2)
            logger.info("Company size configuration completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure company size: {e}")
            return False
    
    def apply_scope_settings(self, driver) -> bool:
        """Apply scope settings"""
        try:
            logger.info("Applying scope settings...")
            
            apply_selectors = [
                '#btn_add_scope_apply',
                'button.btn.btn-cta',
                '//button[contains(text(),"Apply")]',
            ]
            
            apply_clicked = False
            for selector in apply_selectors:
                try:
                    if selector.startswith('//'):
                        apply_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        apply_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    driver.execute_script("arguments[0].click();", apply_btn)
                    logger.info(f"Apply button clicked using selector: {selector}")
                    apply_clicked = True
                    break
                except Exception as e:
                    logger.debug(f"Apply selector {selector} failed: {e}")
                    continue
            
            if not apply_clicked:
                logger.error("Could not find or click Apply button with any selector")
                return False
                
            time.sleep(3)
            logger.info("Scope settings applied")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply scope settings: {e}")
            return False
    
    def proceed_to_pricing(self, driver) -> bool:
        """Proceed to pricing section"""
        try:
            logger.info("Proceeding to Pricing section...")
            next_pricing_btn = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.btn.btn-cta.sa-wizard-btn-next'))
            )
            driver.execute_script("arguments[0].click();", next_pricing_btn)
            time.sleep(2)
            logger.info("Moved to Pricing section")
            return True
        except Exception as e:
            logger.error(f"Failed to proceed to pricing: {e}")
            return False
    
    def adjust_pricing_factors(self, driver) -> bool:
        """Click Adjust Pricing Factors button"""
        try:
            logger.info("Clicking 'Adjust Pricing Factors' button...")
            
            adjust_pricing_selectors = [
                '//button[contains(text(),"Adjust Pricing Factors")]',
                '//button[@onclick="javascript: adjustJobCompensableFactor(this);"]',
                '//button[span[@class="icon-edit"] and contains(text(),"Adjust Pricing Factors")]',
                'button.btn.btn-default.btn-cta[onclick*="adjustJobCompensableFactor"]',
                '//button[contains(@class,"btn-cta") and contains(text(),"Adjust")]'
            ]
            
            adjust_btn_clicked = False
            for selector in adjust_pricing_selectors:
                try:
                    if selector.startswith('//'):
                        adjust_btn = WebDriverWait(driver, 15).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        adjust_btn = WebDriverWait(driver, 15).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    logger.info(f"Adjust Pricing Factors button found with selector: {selector}")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", adjust_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", adjust_btn)
                    logger.info("Adjust Pricing Factors button clicked")
                    adjust_btn_clicked = True
                    break
                    
                except Exception as e:
                    logger.debug(f"Adjust Pricing selector {selector} failed: {e}")
                    continue
            
            if not adjust_btn_clicked:
                logger.info("Trying fallback method to find Adjust button...")
                try:
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    for btn in all_buttons:
                        if "adjust" in btn.text.lower() and "pricing" in btn.text.lower():
                            logger.info(f"Found Adjust Pricing button: {btn.text}")
                            driver.execute_script("arguments[0].click();", btn)
                            adjust_btn_clicked = True
                            break
                except Exception as e:
                    logger.warning(f"Fallback button search failed: {e}")
            
            if not adjust_btn_clicked:
                logger.error("Could not find Adjust Pricing Factors button")
                return False
                
            time.sleep(3)
            logger.info("Pricing factors page loaded")
            return True
            
        except Exception as e:
            logger.error(f"Failed to adjust pricing factors: {e}")
            return False
    
    def set_experience_years(self, driver, experience_years: int) -> bool:
        """Set experience years"""
        try:
            logger.info(f"Setting experience years: {experience_years}")
            
            # Ensure the experience dropdown/modal is open
            try:
                exp_dropdown = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.dropdown-toggle.text-black[data-toggle="dropdown"]'))
                )
                driver.execute_script("arguments[0].click();", exp_dropdown)
                time.sleep(1)
            except Exception:
                pass  # Already open

            # Select "Use specific years" radio button
            try:
                use_specific_radio = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "UseSpecifyRange"))
                )
                if not use_specific_radio.is_selected():
                    driver.execute_script("arguments[0].click();", use_specific_radio)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Radio button selection: {e}")

            # Find and fill the experience input field
            logger.info("Looking for experience input field...")
            try:
                experience_input = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.ID, "experience-slider-value"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", experience_input)
                experience_input.clear()
                driver.execute_script("arguments[0].value = '';", experience_input)
                time.sleep(0.5)
                experience_input.send_keys(str(experience_years))
                time.sleep(0.5)
                driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                    arguments[0].dispatchEvent(new Event('blur', {bubbles: true}));
                """, experience_input)
                logger.info(f"Experience input value set to: {experience_input.get_attribute('value')}")
                time.sleep(1)
            except Exception as e:
                logger.error("Could not find experience input field")
                return False

            # Click the Apply button for experience changes
            logger.info("Looking for Apply button in experience section...")
            try:
                apply_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//button[contains(text(),"Apply") and @onclick="experienceApply();"]'))
                )
                driver.execute_script("arguments[0].click();", apply_btn)
                logger.info("Apply button clicked")
            except Exception as e:
                logger.warning(f"Apply button handling: {e}")

            time.sleep(2)
            logger.info(f"Experience successfully set to {experience_years} years")
            return True

        except Exception as e:
            logger.error(f"Error setting experience: {e}")
            return False
    
    def set_education_level(self, driver, education_level: str) -> bool:
        """Set education level"""
        try:
            logger.info(f"Selecting education level: {education_level}")
            
            # Click the Education dropdown
            edu_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-toggle="dropdown"].educationlabel.PricingFactors'))
            )
            driver.execute_script("arguments[0].click();", edu_dropdown)
            time.sleep(1)

            # Select the desired education option by link text
            edu_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f'//ul[contains(@class,"dropdown-menu") and contains(@id,"EducationCodeBox")]//a[normalize-space()="{education_level}"]'))
            )
            driver.execute_script("arguments[0].click();", edu_option)
            logger.info(f"Education level '{education_level}' selected")
            time.sleep(1)
            return True
        except Exception as e:
            logger.error(f"Error selecting education: {e}")
            return False
    
    def recalculate_compensation(self, driver) -> bool:
        """Click Recalculate Comp button"""
        try:
            logger.info("Clicking 'Recalculate Comp' button...")
            recalc_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.btn.btn-primary.btn-recalculate'))
            )
            driver.execute_script("arguments[0].click();", recalc_btn)
            logger.info("Recalculate Comp button clicked")
            time.sleep(3)  # Wait for recalculation to finish
            return True
        except Exception as e:
            logger.error(f"Error clicking Recalculate Comp: {e}")
            return False
    
    def switch_to_data_grid(self, driver) -> bool:
        """Switch to Data Grid tab"""
        try:
            logger.info("Switching to 'Data Grid' tab...")
            data_grid_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "btnSingleDatagridTab"))
            )
            driver.execute_script("arguments[0].click();", data_grid_btn)
            logger.info("Data Grid tab clicked")
            time.sleep(2)  # Wait for data grid to load
            return True
        except Exception as e:
            logger.error(f"Error clicking Data Grid tab: {e}")
            return False
    
    def extract_table_data(self, driver) -> Dict[str, Any]:
        """Extract salary data from the Data Grid table"""
        try:
            logger.info("Extracting data from Data Grid table...")
            print("🔍 Looking for Data Grid table...")
            
            # Wait for the Data Grid table to be visible
            table = WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, '//table[contains(@class,"tablesaw")]'))
            )
            print("✅ Data Grid table found")
            logger.info("✅ Data Grid table found and visible")

            # Extract headers
            print("📋 Extracting table headers...")
            logger.info("📋 Extracting table headers...")
            headers = []
            header_row = table.find_element(By.TAG_NAME, "thead").find_elements(By.TAG_NAME, "th")
            for th in header_row:
                headers.append(th.text.strip())
            print(f"   Found {len(headers)} headers: {', '.join(headers)}")
            logger.info(f"📋 Found {len(headers)} headers: {', '.join(headers)}")

            # Extract rows
            print("📊 Extracting table rows...")
            logger.info("📊 Extracting table rows...")
            rows = []
            for tr in table.find_element(By.TAG_NAME, "tbody").find_elements(By.TAG_NAME, "tr"):
                row = []
                for td in tr.find_elements(By.TAG_NAME, "td"):
                    row.append(td.text.strip())
                rows.append(row)
            
            print(f"   Extracted {len(rows)} rows of data")
            logger.info(f"📊 Extracted {len(rows)} rows of data")

            # Also get full page text for additional context
            print("📄 Extracting full page text...")
            logger.info("📄 Extracting full page text...")
            page_text = driver.find_element(By.TAG_NAME, "body").text
            print(f"   Page text length: {len(page_text)} characters")
            logger.info(f"📄 Page text length: {len(page_text)} characters")

            # Log detailed data extraction results
            logger.info("=" * 60)
            logger.info("📊 DATA EXTRACTION RESULTS:")
            logger.info("=" * 60)
            logger.info(f"📋 Headers ({len(headers)}): {', '.join(headers)}")
            logger.info(f"📊 Rows: {len(rows)}")
            logger.info(f"📄 Page Text: {len(page_text)} characters")
            
            if rows:
                logger.info("📋 Sample Rows:")
                for i, row in enumerate(rows[:3]):  # Show first 3 rows in detail
                    logger.info(f"   Row {i+1}: {' | '.join(str(cell) for cell in row)}")
                
                if len(rows) > 3:
                    logger.info(f"   ... and {len(rows) - 3} more rows")
            
            logger.info("=" * 60)

            logger.info(f"Successfully extracted {len(rows)} rows with {len(headers)} columns")
            print(f"✅ Data extraction completed: {len(rows)} rows × {len(headers)} columns")
            
            return {
                "headers": headers,
                "rows": rows,
                "full_page_text": page_text,
                "total_rows": len(rows)
            }
            
        except Exception as e:
            logger.error(f"Error extracting table data: {e}")
            print(f"❌ Error extracting table data: {e}")
            # Return basic page text if table extraction fails
            try:
                print("🔄 Attempting to extract basic page text...")
                logger.info("🔄 Attempting to extract basic page text...")
                page_text = driver.find_element(By.TAG_NAME, "body").text
                print(f"   Basic page text extracted: {len(page_text)} characters")
                logger.info(f"📄 Basic page text extracted: {len(page_text)} characters")
                
                # Log what we could extract
                logger.error("=" * 60)
                logger.error("❌ TABLE EXTRACTION FAILED - FALLBACK DATA:")
                logger.error("=" * 60)
                logger.error(f"📄 Page Text Length: {len(page_text)} characters")
                logger.error(f"❌ Error: {str(e)}")
                logger.error("=" * 60)
                
                return {
                    "headers": [],
                    "rows": [],
                    "full_page_text": page_text,
                    "total_rows": 0,
                    "error": str(e)
                }
            except Exception as e2:
                print(f"❌ Failed to extract even basic page text: {e2}")
                logger.error(f"❌ Failed to extract even basic page text: {e2}")
                
                logger.error("=" * 60)
                logger.error("❌ COMPLETE EXTRACTION FAILURE:")
                logger.error("=" * 60)
                logger.error(f"❌ Table extraction error: {str(e)}")
                logger.error(f"❌ Page text extraction error: {str(e2)}")
                logger.error("=" * 60)
                
                return {
                    "headers": [],
                    "rows": [],
                    "full_page_text": "",
                    "total_rows": 0,
                    "error": f"Table extraction failed: {e}, Page text extraction failed: {e2}"
                }
    
    def scrape_salary_data(self, job_title: str, city: str, education_level: str = "Bachelor's", 
                          experience_years: int = 10) -> Dict[str, Any]:
        """Main scraping function that orchestrates the entire process"""
        start_time = time.time()
        
        logger.info(f"Starting salary data scraping for:")
        logger.info(f"  Job Title: {job_title}")
        logger.info(f"  City: {city}")
        logger.info(f"  Education: {education_level}")
        logger.info(f"  Experience: {experience_years} years")
        
        print(f"🔐 Step 1: Initializing Chrome driver...")
        driver = self.driver_manager.get_driver()
        if not driver:
            print("❌ Failed to initialize Chrome driver")
            return {
                "success": False,
                "error": "Failed to initialize Chrome driver",
                "data": {},
                "scraping_time": 0
            }

        try:
            # Step 1: Login
            print("🔐 Step 2: Logging into Salary.com...")
            if not self.login(driver):
                raise Exception("Login failed")
            print("✅ Login successful")
            
            # Step 2: Navigate to Market Data
            print("🧭 Step 3: Navigating to Market Data...")
            if not self.navigate_to_market_data(driver):
                raise Exception("Failed to navigate to Market Data")
            print("✅ Market Data page reached")
            
            # Step 3: Search for job title
            print(f"🔍 Step 4: Searching for job title: {job_title}...")
            if not self.search_job_title(driver, job_title):
                raise Exception("Failed to search for job title")
            print("✅ Job title search completed")
            
            # Step 4: Select first job
            print("📋 Step 5: Selecting first job from results...")
            if not self.select_first_job(driver):
                raise Exception("Failed to select first job")
            print("✅ Job selected")
            
            # Step 5: Proceed to Scope
            print("⚙️  Step 6: Proceeding to Scope configuration...")
            if not self.proceed_to_scope(driver):
                raise Exception("Failed to proceed to Scope")
            print("✅ Scope page reached")
            
            # Step 6: Click New Scope
            print("🆕 Step 7: Creating new scope...")
            if not self.click_new_scope(driver):
                raise Exception("Failed to click New Scope")
            print("✅ New scope created")
            
            # Step 7: Configure Geography
            print(f"🌍 Step 8: Configuring geography for {city}...")
            if not self.configure_geography(driver, city):
                raise Exception("Failed to configure geography")
            print("✅ Geography configured")
            
            # Step 8: Configure Industry
            print("🏭 Step 9: Configuring industry settings...")
            if not self.configure_industry(driver):
                raise Exception("Failed to configure industry")
            print("✅ Industry configured")
            
            # Step 9: Configure Company Size
            print("🏢 Step 10: Configuring company size...")
            if not self.configure_company_size(driver):
                raise Exception("Failed to configure company size")
            print("✅ Company size configured")
            
            # Step 10: Apply Scope Settings
            print("✅ Step 11: Applying scope settings...")
            if not self.apply_scope_settings(driver):
                raise Exception("Failed to apply scope settings")
            print("✅ Scope settings applied")
            
            # Step 11: Proceed to Pricing
            print("💰 Step 12: Proceeding to pricing configuration...")
            if not self.proceed_to_pricing(driver):
                raise Exception("Failed to proceed to pricing")
            print("✅ Pricing page reached")
            
            # Step 12: Adjust Pricing Factors
            print("⚖️  Step 13: Adjusting pricing factors...")
            if not self.adjust_pricing_factors(driver):
                raise Exception("Failed to adjust pricing factors")
            print("✅ Pricing factors adjusted")
            
            # Step 13: Set Experience Years
            print(f"⏰ Step 14: Setting experience years to {experience_years}...")
            if not self.set_experience_years(driver, experience_years):
                logger.warning("Failed to set experience years, continuing anyway")
                print("⚠️  Failed to set experience years, continuing anyway")
            else:
                print("✅ Experience years set")
            
            # Step 14: Set Education Level
            print(f"🎓 Step 15: Setting education level to {education_level}...")
            if not self.set_education_level(driver, education_level):
                logger.warning("Failed to set education level, continuing anyway")
                print("⚠️  Failed to set education level, continuing anyway")
            else:
                print("✅ Education level set")
            
            # Step 15: Recalculate Compensation
            print("🔄 Step 16: Recalculating compensation...")
            if not self.recalculate_compensation(driver):
                raise Exception("Failed to recalculate compensation")
            print("✅ Compensation recalculated")
            
            # Step 16: Switch to Data Grid
            print("📊 Step 17: Switching to data grid view...")
            if not self.switch_to_data_grid(driver):
                raise Exception("Failed to switch to Data Grid")
            print("✅ Data grid view active")
            
            # Step 17: Extract Table Data
            print("📋 Step 18: Extracting table data...")
            table_data = self.extract_table_data(driver)
            print("✅ Table data extracted")
            
            scraping_time = round(time.time() - start_time, 2)
            
            # LOG THE FINAL RESULTS TO SERVER TERMINAL
            logger.info("=" * 80)
            logger.info("🎉 SALARY SCRAPING COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info(f"⏱️  Total Time: {scraping_time} seconds")
            logger.info(f"📊 Job Title: {job_title}")
            logger.info(f"🏙️  City: {city}")
            logger.info(f"🎓 Education: {education_level}")
            logger.info(f"⏰ Experience: {experience_years} years")
            
            # Log table headers
            headers = table_data.get("headers", [])
            if headers:
                logger.info(f"📋 Table Headers ({len(headers)} columns):")
                logger.info("   " + " | ".join(headers))
            
            # Log sample data rows
            rows = table_data.get("rows", [])
            if rows:
                logger.info(f"📊 Data Extracted: {len(rows)} rows")
                logger.info("📋 Sample Data (first 5 rows):")
                for i, row in enumerate(rows[:5]):
                    logger.info(f"   Row {i+1}: {' | '.join(str(cell) for cell in row)}")
                
                if len(rows) > 5:
                    logger.info(f"   ... and {len(rows) - 5} more rows")
                
                # Log summary statistics
                logger.info("📈 Summary Statistics:")
                logger.info(f"   - Total Rows: {len(rows)}")
                logger.info(f"   - Total Columns: {len(headers)}")
                logger.info(f"   - Scraping Time: {scraping_time}s")
                logger.info(f"   - Success: ✅")
            else:
                logger.warning("⚠️  No table data extracted!")
            
            logger.info("=" * 80)
            
            return {
                "success": True,
                "data": {
                    "job_title": job_title,
                    "city": city,
                    "education_level": education_level,
                    "experience_years": experience_years,
                    "table_headers": table_data.get("headers", []),
                    "table_rows": table_data.get("rows", []),
                    "full_page_text": table_data.get("full_page_text", ""),
                    "total_rows": table_data.get("total_rows", 0)
                },
                "scraping_time": scraping_time,
                "error": table_data.get("error")
            }
            
        except Exception as e:
            scraping_time = round(time.time() - start_time, 2)
            logger.error(f"Salary data scraping failed: {e}")
            print(f"❌ Scraping failed at step: {str(e)}")
            
            # Log the failure details
            logger.error("=" * 80)
            logger.error("❌ SALARY SCRAPING FAILED!")
            logger.error("=" * 80)
            logger.error(f"⏱️  Time Spent: {scraping_time} seconds")
            logger.error(f"📊 Job Title: {job_title}")
            logger.error(f"🏙️  City: {city}")
            logger.error(f"🎓 Education: {education_level}")
            logger.error(f"⏰ Experience: {experience_years} years")
            logger.error(f"❌ Error: {str(e)}")
            logger.error("=" * 80)
            
            return {
                "success": False,
                "error": str(e),
                "data": {},
                "scraping_time": scraping_time
            }
            
        finally:
            print("🧹 Cleaning up Chrome driver...")
            self.driver_manager.quit_driver()
            print("✅ Chrome driver closed")

# ---------------- MCP Tools ---------------- #
scraper = SalaryComScraper()

class SalaryRequest(BaseModel):
    job_title: str
    city: str
    education_level: str = "Bachelor's"
    experience_years: int = 10

@mcp_salary.tool()
def scrape_salary_compensation(job_title: str, city: str, education_level: str = "Bachelor's", 
                              experience_years: int = 10) -> Dict[str, Any]:
    """
    Scrape comprehensive salary and compensation data from Salary.com CompAnalyst.
    
    This tool performs the complete workflow:
    1. Login to Salary.com
    2. Navigate to Market Data
    3. Search for the specified job title
    4. Configure geographic scope (city)
    5. Set industry filters (All Industries)
    6. Set company size filters (50-100 FTEs)
    7. Adjust pricing factors (experience and education)
    8. Extract detailed compensation data from Data Grid
    
    Args:
        job_title: The job title to search for (e.g., "Software Engineer")
        city: The city to analyze (e.g., "Washington")
        education_level: Education level (default: "Bachelor's")
        experience_years: Years of experience (default: 10)
    
    Returns:
        Dictionary with salary data including table headers, rows, and metadata
    """
    logger.info(f"MCP Tool called: scrape_salary_compensation")
    logger.info(f"  Parameters: {job_title}, {city}, {education_level}, {experience_years}")
    
    print(f"\n🚀 Starting Salary.com scraping for: {job_title} in {city}")
    print(f"   Education: {education_level}, Experience: {experience_years} years")
    print("=" * 60)
    
    # Call the scraper
    result = scraper.scrape_salary_data(
        job_title=job_title,
        city=city, 
        education_level=education_level,
        experience_years=experience_years
    )
    
    # LOG THE FINAL RESULTS TO SERVER TERMINAL
    logger.info("=" * 80)
    logger.info("🎯 MCP TOOL RESULTS:")
    logger.info("=" * 80)
    
    if result.get("success"):
        data = result.get("data", {})
        scraping_time = result.get("scraping_time", 0)
        
        logger.info(f"✅ SUCCESS: Scraping completed in {scraping_time}s")
        logger.info(f"📊 Job Title: {data.get('job_title', 'N/A')}")
        logger.info(f"🏙️  City: {data.get('city', 'N/A')}")
        logger.info(f"📋 Total Rows: {data.get('total_rows', 0)}")
        
        # Log table headers
        headers = data.get("table_headers", [])
        if headers:
            logger.info(f"📋 Table Headers ({len(headers)} columns):")
            logger.info("   " + " | ".join(headers))
        
        # Log sample data rows
        rows = data.get("table_rows", [])
        if rows:
            logger.info(f"📊 Sample Data (showing first 5 rows):")
            for i, row in enumerate(rows[:5]):
                logger.info(f"   Row {i+1}: {' | '.join(str(cell) for cell in row)}")
            
            if len(rows) > 5:
                logger.info(f"   ... and {len(rows) - 5} more rows")
            
            # Log summary statistics
            logger.info(f"📈 Summary:")
            logger.info(f"   - Data extracted: {len(rows)} rows")
            logger.info(f"   - Columns: {len(headers)}")
            logger.info(f"   - Scraping time: {scraping_time}s")
            logger.info(f"   - Success: ✅")
        else:
            logger.warning("⚠️  No table data found in results!")
        
    else:
        error = result.get("error", "Unknown error")
        scraping_time = result.get("scraping_time", 0)
        
        logger.error(f"❌ FAILED: {error}")
        logger.error(f"⏱️  Time spent: {scraping_time}s")
        logger.error(f"   - Success: ❌")
    
    logger.info("=" * 80)
    
    # Display results in terminal (for direct testing)
    if result.get("success"):
        data = result.get("data", {})
        scraping_time = result.get("scraping_time", 0)
        
        print(f"\n✅ Scraping completed successfully in {scraping_time}s")
        print(f"📊 Job Title: {data.get('job_title', 'N/A')}")
        print(f"🏙️  City: {data.get('city', 'N/A')}")
        print(f"📋 Total Rows: {data.get('total_rows', 0)}")
        
        # Show table headers
        headers = data.get("table_headers", [])
        if headers:
            print(f"\n📋 Table Headers ({len(headers)} columns):")
            print("   " + " | ".join(headers))
        
        # Show first few rows of data
        rows = data.get("table_rows", [])
        if rows:
            print(f"\n📊 Sample Data (showing first 3 rows):")
            for i, row in enumerate(rows[:3]):
                print(f"   Row {i+1}: {' | '.join(str(cell) for cell in row)}")
            
            if len(rows) > 3:
                print(f"   ... and {len(rows) - 3} more rows")
        
        # Show summary statistics if available
        if rows and len(rows) > 0:
            print(f"\n📈 Summary:")
            print(f"   - Data extracted: {len(rows)} rows")
            print(f"   - Columns: {len(headers)}")
            print(f"   - Scraping time: {scraping_time}s")
        
    else:
        error = result.get("error", "Unknown error")
        print(f"\n❌ Scraping failed: {error}")
        print(f"⏱️  Time spent: {result.get('scraping_time', 0)}s")
    
    print("=" * 60)
    return result

@mcp_salary.tool()
def save_salary_data_to_csv(data: Dict[str, Any], filename: str = None) -> Dict[str, Any]:
    """
    Save salary data to CSV file.
    
    Args:
        data: The salary data dictionary returned from scrape_salary_compensation
        filename: Optional filename (will auto-generate if not provided)
    
    Returns:
        Dictionary with save status and file path
    """
    try:
        if not data.get("success") or not data.get("data"):
            return {
                "success": False,
                "error": "No valid data to save",
                "file_path": None
            }
        
        salary_data = data["data"]
        headers = salary_data.get("table_headers", [])
        rows = salary_data.get("table_rows", [])
        
        if not headers or not rows:
            return {
                "success": False,
                "error": "No table data found to save",
                "file_path": None
            }
        
        # Generate filename if not provided
        if not filename:
            job_title = salary_data.get("job_title", "job").replace(" ", "_").lower()
            city = salary_data.get("city", "city").replace(" ", "_").lower()
            timestamp = int(time.time())
            filename = f"salary_data_{job_title}_{city}_{timestamp}.csv"
        
        # Ensure .csv extension
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        # Write to CSV
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        
        logger.info(f"Salary data saved to: {filename}")
        
        return {
            "success": True,
            "file_path": filename,
            "rows_saved": len(rows),
            "columns": len(headers)
        }
        
    except Exception as e:
        logger.error(f"Error saving salary data to CSV: {e}")
        return {
            "success": False,
            "error": str(e),
            "file_path": None
        }

@mcp_salary.tool()
def get_available_education_levels() -> List[str]:
    """
    Get list of available education levels for salary.com scraping.
    
    Returns:
        List of education level options
    """
    return [
        "High School",
        "Some College", 
        "Associate's",
        "Bachelor's",
        "Master's",
        "Doctorate",
        "Professional"
    ]

@mcp_salary.tool()
def health_check_salary() -> Dict[str, Any]:
    """
    Health check for the Salary.com scraping service.
    Tests basic connectivity and login capability.
    
    Returns:
        Dictionary with health status
    """
    logger.info("Running health check for Salary.com scraper...")
    print("🏥 Running Salary.com scraper health check...")
    
    driver_manager = DriverManager()
    print("🔧 Initializing Chrome driver for health check...")
    driver = driver_manager.get_driver(headless=True)
    
    if not driver:
        print("❌ Failed to initialize Chrome driver")
        return {
            "status": "unhealthy",
            "error": "Failed to initialize Chrome driver"
        }
    
    try:
        # Test navigation to salary.com
        print("🌐 Testing Salary.com navigation...")
        logger.info("Testing Salary.com navigation...")
        driver.get(LOGIN_URL)
        
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print("✅ Salary.com page loaded successfully")
        
        # Check if we can find login elements
        print("🔍 Looking for login elements...")
        login_selectors = [
            "input#loginid",
            "input#password", 
            "iframe"
        ]
        
        found_login_elements = False
        for selector in login_selectors:
            try:
                if selector == "iframe":
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    if iframes:
                        driver.switch_to.frame(iframes[0])
                        if "loginid" in driver.page_source:
                            found_login_elements = True
                            print("✅ Login elements found in iframe")
                            break
                        driver.switch_to.default_content()
                else:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    found_login_elements = True
                    print(f"✅ Login element found: {selector}")
                    break
            except TimeoutException:
                print(f"⏰ Timeout finding: {selector}")
                continue
        
        if found_login_elements:
            logger.info("Health check passed - login elements found")
            print("✅ Health check PASSED - Salary.com login page accessible")
            return {
                "status": "healthy",
                "message": "Salary.com login page accessible"
            }
        else:
            print("❌ Health check FAILED - Could not find login elements")
            return {
                "status": "unhealthy", 
                "error": "Could not find login elements on Salary.com"
            }
        
    except Exception as e:
        print(f"❌ Health check FAILED with error: {str(e)}")
        return {
            "status": "unhealthy",
            "error": f"Health check failed: {str(e)}"
        }
    finally:
        print("🧹 Cleaning up health check driver...")
        driver_manager.quit_driver()
        print("✅ Health check driver closed")

@mcp_salary.tool()
def debug_show_last_data() -> Dict[str, Any]:
    """
    Debug tool to show the last scraped data in the server terminal.
    Useful for seeing what was extracted without running the full workflow again.
    
    Returns:
        Dictionary with debug information
    """
    logger.info("🔍 Debug tool called: debug_show_last_data")
    print("🔍 Debug tool called: debug_show_last_data")
    
    try:
        # This is a simple way to see data in the server terminal
        # You can call this tool after scraping to see the results
        
        logger.info("=" * 80)
        logger.info("🔍 DEBUG: LAST SCRAPED DATA")
        logger.info("=" * 80)
        logger.info("📝 Note: This tool shows the last scraping session data")
        logger.info("📝 Call this after scrape_salary_compensation to see results")
        logger.info("=" * 80)
        
        print("🔍 Debug tool called - check server logs for data")
        print("📝 Call this tool after scraping to see the results in server logs")
        
        return {
            "success": True,
            "message": "Debug tool called - check server logs for last scraped data",
            "note": "This tool is for debugging - call it after scraping to see results"
        }
        
    except Exception as e:
        logger.error(f"Debug tool error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ---------------- Test Function ---------------- #
def test_scraper_directly():
    """Test the scraper directly without MCP - useful for debugging"""
    print("🧪 Testing Salary.com scraper directly...")
    print("=" * 60)
    
    try:
        # Test with sample data
        test_job_title = "Software Engineer"
        test_city = "Seattle"
        test_education = "Bachelor's"
        test_experience = 10
        
        print(f"Testing with: {test_job_title} in {test_city}")
        print(f"Education: {test_education}, Experience: {test_experience} years")
        print()
        
        # Create scraper and run test
        test_scraper = SalaryComScraper()
        result = test_scraper.scrape_salary_data(
            job_title=test_job_title,
            city=test_city,
            education_level=test_education,
            experience_years=test_experience
        )
        
        # Display results
        if result.get("success"):
            data = result.get("data", {})
            print(f"\n🎉 Test completed successfully!")
            print(f"📊 Data extracted: {data.get('total_rows', 0)} rows")
            print(f"⏱️  Time taken: {result.get('scraping_time', 0)}s")
            
            # Show sample data
            headers = data.get("table_headers", [])
            rows = data.get("table_rows", [])
            
            if headers and rows:
                print(f"\n📋 Sample data:")
                print("   " + " | ".join(headers))
                for i, row in enumerate(rows[:3]):
                    print(f"   Row {i+1}: {' | '.join(str(cell) for cell in row)}")
                if len(rows) > 3:
                    print(f"   ... and {len(rows) - 3} more rows")
        else:
            print(f"\n❌ Test failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()

# ---------------- Run Server ---------------- #
if __name__ == "__main__":
    logger.info(f"Starting Salary.com MCP Server on port {settings.mcp_salary_server_port}")  # NO CHANGE
    print(f"🚀 Starting Salary.com MCP Server on port {settings.mcp_salary_server_port}")      # NO CHANGE
    print(f"📡 Server will be available at: http://{settings.mcp_salary_host}:{settings.mcp_salary_server_port}/mcp/")  # CHANGED
    print("🔧 To test scraper directly, call: test_scraper_directly()")                       # NO CHANGE
    print("=" * 60)     
    
    # Uncomment the next line to test the scraper directly when starting the server
    # test_scraper_directly()
    
    mcp_salary.run(transport="http", host=settings.mcp_server_bind_host, port=settings.mcp_salary_server_port)