import requests
import hashlib
from collections import defaultdict

# Colors we probed earlier
PROBED_DATA = [
    # DS 4 DIESEL
    {"model": "DS 4 DIESEL", "version": "1SD4A5NP41B0A052", "colors": ["0MM60NN9", "0MM00N9V", "0MM00NA1", "0MP00NSD", "0MM00NPH", "0MM00NGG", "0MM00NBC", "0MM00NSU", "0MP00NWP", "0MM00NHZ", "0MM00NSC", "0MM00N6L", "0MM00N1J"]},
    # DS 7 PERF LINE
    {"model": "DS 7 DS PERFORMANCE Line", "version": "1SX8SUTP41B0A060", "colors": ["0MM60NN9", "0MM00N9V", "0MM00NA1", "0MP00NSD", "0MM00NPH", "0MM00NGG", "0MM00NBC", "0MM00NSU", "0MP00NWP", "0MM00NHZ", "0MM00NSC", "0MM00N6L", "0MM00N1J"]}
]

def get_image_hash(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return hashlib.md5(r.content).hexdigest(), len(r.content)
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return None, 0

def main():
    print("🕵️ Verifying images to detect fallbacks...")

    for item in PROBED_DATA:
        model = item["model"]
        version = item["version"]
        print(f"\n🚗 Analyzing: {model} ({version})")
        
        hashes = defaultdict(list)
        
        for color in item["colors"]:
            url = f"https://visuel3d-secure.citroen.com/V3DImage.ashx?client=DI1&version={version}&color={color}&width=300&ratio=1&view=001&format=jpg"
            img_hash, size = get_image_hash(url)
            
            if img_hash:
                hashes[img_hash].append(color)
                # print(f"   Color {color}: Hash={img_hash[:8]} Size={size}")
            else:
                print(f"   Color {color}: Failed to fetch")

        # Analyze results
        unique_hashes = len(hashes)
        print(f"   Found {unique_hashes} unique image(s) across {len(item['colors'])} probed colors.")
        
        if unique_hashes == 1:
            print("   ⚠️  WARNING: All colors return the SAME image. API is likely returning a fallback.")
        else:
            for h, colors in hashes.items():
                if len(colors) > 1:
                    print(f"   ⚠️  Hash {h[:8]} shared by: {', '.join(colors)} (Likely invalid/fallback group)")
                else:
                    print(f"   ✅  Unique image for: {colors[0]}")

if __name__ == "__main__":
    main()
