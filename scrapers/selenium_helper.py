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
    # --- CI stability + lower RAM (mitigates /dev/shm crashes & OOM -> exit 143) ---
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--mute-audio")
    # Don't render page images: the feed pulls og_image straight from the API,
    # so the page's own images are dead weight (RAM + load time). The B2B rate
    # comes from JS/WebSocket, not images, so this is safe.
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = 'eager'
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45) # Prevent hanging on bad loads
    return driver

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

def get_b2b_price_selenium(url, driver=None, max_wait=15):
    """Extract the B2B installment price from a Stellantis WordPress product page.

    The site uses WP Rocket lazy loading + the Stellantis Financial Calculator
    (FCP, over WebSocket). We trigger lazy loading via simulated user interaction,
    then *poll* for the B2B rate in #top_sekcja_wysokosc_raty and return the moment
    it appears — instead of sleeping a fixed ~23s budget per car. ``max_wait``
    (seconds) bounds how long we wait before giving up on a slow/missing rate.
    """
    should_quit = False
    if driver is None:
        driver = init_driver()
        should_quit = True

    try:
        driver.get(url)
        time.sleep(0.5)  # let the DOM + WP Rocket scripts attach

        # Trigger WP Rocket lazy loading (the calculator boots on user interaction)
        _trigger_wp_rocket(driver)

        # Poll for the FCP calculator to compute and fill the rata element.
        deadline = time.monotonic() + max_wait
        retriggered = False
        while time.monotonic() < deadline:
            val = driver.execute_script(
                "var el=document.getElementById('top_sekcja_wysokosc_raty');"
                "return el?el.textContent.trim():'';"
            )
            if val:
                # Extract digits only: "1 085 zł" -> "1085"
                price = re.sub(r'[^\d]', '', val)
                if price:
                    return price
            # Re-fire the interaction once (~2s in) in case the first didn't take.
            if not retriggered and time.monotonic() > deadline - max_wait + 2:
                _trigger_wp_rocket(driver)
                retriggered = True
            time.sleep(0.4)

        # Fallback: check sticky footer
        footer_val = driver.execute_script(
            "var el=document.querySelector('.footer-sticky-rata-wartosc');"
            "return el?el.textContent.trim():'';"
        )
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
