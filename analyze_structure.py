import requests
import re

url = "https://sklep.dsautomobiles.pl/sklep/"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

# Check for WooCommerce
if "woocommerce" in r.text:
    print("Detected WooCommerce!")

# Check for other car-specific classes
if "car-item" in r.text or "vehicle" in r.text:
    print("Detected car-specific HTML classes")

# Try to find the API endpoint used for filtering/loading
# Look for 'admin-ajax.php' which is standard for WP AJAX
if "admin-ajax.php" in r.text:
    print("Detected admin-ajax.php")
