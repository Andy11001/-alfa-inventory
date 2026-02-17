from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
import time
import re

def init_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def _trigger_wp_rocket(driver):
    """Trigger WP Rocket lazy loading by simulating user interaction.
    Uses both ActionChains (real CDP events) and JS dispatchEvent for reliability."""
    # Real mouse event via CDP — move to body element to avoid offset accumulation
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        ActionChains(driver).move_to_element_with_offset(body, 100, 100).perform()
    except:
        pass
    # JS-dispatched events as backup
    driver.execute_script("""
        document.dispatchEvent(new MouseEvent('mousemove', {clientX: 100, clientY: 100}));
        document.dispatchEvent(new Event('scroll'));
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'a'}));
        window.dispatchEvent(new Event('scroll'));
    """)
    # Scroll to trigger intersection observers
    driver.execute_script("window.scrollBy(0, 300);")

def get_b2b_price_selenium(url, driver=None):
    """Extract B2B installment price from DS Automobiles product page.
    
    The DS website uses WP Rocket lazy loading + Stellantis Financial Calculator (FCP).
    We trigger lazy loading via simulated user interaction, then wait for the WebSocket
    calculator to compute and display the B2B rate in #top_sekcja_wysokosc_raty.
    """
    should_quit = False
    if driver is None:
        driver = init_driver()
        should_quit = True
        
    try:
        driver.get(url)
        time.sleep(2)
        
        # Trigger WP Rocket lazy loading
        _trigger_wp_rocket(driver)
        time.sleep(1)
        _trigger_wp_rocket(driver)  # Fire twice for reliability
        
        # Wait for FCP calculator to compute and fill the rata element
        for attempt in range(10):
            time.sleep(2)
            val = driver.execute_script("""
                var el = document.getElementById('top_sekcja_wysokosc_raty');
                return el ? el.textContent.trim() : '';
            """)
            if val and val.strip():
                # Extract digits only: "1 085 zł" -> "1085"
                price = re.sub(r'[^\d]', '', val)
                if price:
                    return price
        
        # Fallback: check sticky footer
        footer_val = driver.execute_script("""
            var el = document.querySelector('.footer-sticky-rata-wartosc');
            return el ? el.textContent.trim() : '';
        """)
        if footer_val:
            price = re.sub(r'[^\d]', '', footer_val)
            if price and len(price) >= 3:
                return price
        
        return None
        
    except Exception as e:
        print(f"Selenium Error on {url}: {e}")
        return None
    finally:
        if should_quit:
            driver.quit()
