"""Helper functions for extracting data from LinkedIn pages"""
import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from .browser_helper import human_delay, smooth_scroll


def click_show_all(driver, section):
    """Click 'Show all' link in section"""
    try:
        smooth_scroll(driver, section)
        human_delay(0.5, 0.8)
        
        selectors = [
            ".//a[contains(text(), 'Show all')]",
            ".//a[contains(., 'Show all')]",
            ".//div[contains(@class, 'pvs-list__footer')]//a",
        ]
        
        for selector in selectors:
            try:
                button = section.find_element(By.XPATH, selector)
                button_text = button.text.strip()
                print(f"  Found: '{button_text}'")
                driver.execute_script("arguments[0].click();", button)
                print("  ✓ Clicked 'Show all'")
                human_delay(2, 2.5)
                return True
            except NoSuchElementException:
                continue
        
        print("  ⚠ No 'Show all' button found")
        return False
    except Exception as e:
        print(f"  Error clicking show all: {e}")
        return False


def click_back_arrow(driver):
    """Click back arrow to return to main profile"""
    try:
        print("  Clicking back arrow...")
        
        selectors = [
            "//button[@aria-label='Back']",
            "//button[contains(@class, 'artdeco-button') and contains(@aria-label, 'Back')]",
            "//button[contains(@class, 'scaffold-layout__back-button')]",
        ]
        
        for selector in selectors:
            try:
                back_button = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].click();", back_button)
                print("  ✓ Clicked back arrow")
                human_delay(1.5, 2)
                return True
            except NoSuchElementException:
                continue
        
        print("  ⚠ Back button not found, using browser back")
        driver.back()
        human_delay(1.5, 2)
        return True
        
    except Exception as e:
        print(f"  Error clicking back: {e}")
        return False


def extract_items_from_detail_page(driver):
    """Extract items from detail page after clicking 'Show all'"""
    items = []
    
    print("  Waiting for detail page to load...")
    human_delay(2, 2.5)
    
    driver.execute_script("window.scrollTo(0, 0);")
    human_delay(1, 1.5)
    
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    human_delay(0.8, 1)
    
    selectors = [
        "//main//ul[contains(@class, 'pvs-list')]/li[contains(@class, 'pvs-list__paged-list-item')]",
        "//main//ul[contains(@class, 'pvs-list')]/li",
        "//div[contains(@class, 'scaffold-finite-scroll__content')]//ul/li",
        "//main//ul/li[contains(@class, 'artdeco-list__item')]",
    ]
    
    for selector in selectors:
        items = driver.find_elements(By.XPATH, selector)
        if items and len(items) > 0:
            print(f"  ✓ Found {len(items)} items using selector")
            break
    
    if not items:
        print("  ⚠ No items found on detail page!")
    
    return items
