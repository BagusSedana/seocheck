import sys
import os
import asyncio
import socket

# Add current dir to path
sys.path.insert(0, os.getcwd())

# Mock models and database for auth test
class MockUser:
    id = 1
    email = "test@example.com"
    is_active = True
    tier = "free"

# Since we can't easily mock the whole DB/jose setup without installing more things,
# we'll just test the logic we changed in crawler.py specifically.

from scanner.crawler import crawl

async def test_crawler():
    print("Testing crawler with public URL...")
    result = await crawl("https://google.com")
    if result.get("error"):
        print(f"FAILED: {result['error']}")
    else:
        print(f"SUCCESS: Crawled google.com, status {result['status_code']}")

    print("\nTesting crawler with internal IP (SSRF test)...")
    result = await crawl("http://127.0.0.1")
    if "dilarang" in str(result.get("error")):
        print(f"SUCCESS: SSRF detected and blocked: {result['error']}")
    else:
        print(f"FAILED: SSRF check bypassed or different error: {result.get('error')}")

    print("\nTesting crawler with hostname resolving to internal IP...")
    # 'localhost' should resolve to 127.0.0.1
    result = await crawl("http://localhost")
    if "dilarang" in str(result.get("error")):
        print(f"SUCCESS: SSRF (localhost) detected and blocked: {result['error']}")
    else:
        print(f"FAILED: SSRF check bypassed: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(test_crawler())
