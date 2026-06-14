import sys
from trendradar.trends.fetcher import TrendsFetcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def test_fetcher():
    try:
        print("Testing TrendsFetcher...")
        fetcher = TrendsFetcher(geo="CO")
        print("Getting trending keywords...")
        keywords = fetcher.get_trending_keywords(geo="CO")
        print(f"Keywords retrieved: {keywords[:5]}")
        if not keywords:
            print("No keywords retrieved.")
            return False
            
        print("Test successful!")
        return True
    except Exception as e:
        print(f"Error during test: {e}")
        return False

if __name__ == "__main__":
    success = test_fetcher()
    sys.exit(0 if success else 1)
