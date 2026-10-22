# cookie_extractor.py - May not work as expected in some cases
import asyncio
import json
import os
from playwright.async_api import async_playwright

# The URL to open for login
LOGIN_URL = "https://suno.com"
# The output file your main script expects
COOKIE_FILE = "cookie.txt"

async def main():
    print("🚀 Starting automated login process...")
    async with async_playwright() as p:
        # Launch a visible browser window
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"🌐 Opening browser to: {LOGIN_URL}")
        print("👉 Please log in to your Suno account in the browser window.")
        print("   (You have up to 5 minutes to complete the login.)")
        
        await page.goto(LOGIN_URL)

        # Wait until the user is logged in by checking for a specific cookie
        # or a URL change. Here, we wait for the '__client' cookie to appear.
        try:
            await context.wait_for_event(
                "response", 
                predicate=lambda r: "auth.suno.com" in r.url and r.status == 200,
                timeout=300000 # 5-minute timeout
            )
            # A more reliable check: poll for the necessary cookies
            cookies = []
            for _ in range(60): # Poll for up to 60 seconds
                cookies = await context.cookies()
                if any(c['name'] == '__client' for c in cookies):
                    break
                await asyncio.sleep(1)

        except Exception as e:
            print(f"⏰ Login wait timed out or failed: {e}")
            # Try to get cookies anyway
            cookies = await context.cookies()

        # Filter and save the cookies your downloader needs
        print("🍪 Extracting cookies...")
        suno_cookies = []
        for cookie in cookies:
            if "suno.com" in cookie.get("domain", ""):
                # Map Playwright cookie format to the JSON format your script expects
                cookie_dict = {
                    "domain": cookie.get("domain"),
                    "expirationDate": cookie.get("expires"),
                    "hostOnly": not cookie.get("domain", "").startswith("."),
                    "httpOnly": cookie.get("httpOnly"),
                    "name": cookie.get("name"),
                    "path": cookie.get("path"),
                    "sameSite": cookie.get("sameSite", "Lax"), # Playwright uses 'Lax', 'Strict', 'None'
                    "secure": cookie.get("secure"),
                    "session": False,
                    "storeId": "0",
                    "value": cookie.get("value")
                }
                suno_cookies.append(cookie_dict)

        if not suno_cookies:
            print("❌ No Suno cookies were captured. Login may have failed.")
        else:
            with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                json.dump(suno_cookies, f, indent=2)
            print(f"✅ Successfully saved {len(suno_cookies)} cookies to '{COOKIE_FILE}'.")
            print("   Your 'sunoDownloader.py' will now use these cookies.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
