import requests

BASE = "https://www.dsautomobiles.pl/sccf/prod/ds/publish/data/fccf_mv/scope"
SUFFIXES = [
    "//3123.json",
    "//3123D.json",
    "//3123DS.json",
    "//3123D81.json", # 81 might be DS? (83 is Alfa)
    "//PL.json",
    "//PL_pl.json"
]

def main():
    print("🕵️ Hunting for DS SCCF Scope...")
    for s in SUFFIXES:
        url = BASE + s
        print(f"Trying: {url}")
        try:
            r = requests.get(url, timeout=2)
            print(f"   Status: {r.status_code}")
            if r.status_code == 200:
                print("   🎉 FOUND!")
                print(r.text[:200])
                break
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    main()
