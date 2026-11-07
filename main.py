
import asyncio
from playwright.async_api import async_playwright
from browser_observer import observe_page


async def main():
    website_url = input("Enter website URL: ").strip()

    if not website_url:
        print("Please enter a website URL.")
        return

    if not website_url.startswith(("http://", "https://")):
        website_url = "https://" + website_url

    async with async_playwright() as p:
        browser = None

        try:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            print(f"\nOpening website: {website_url}")

            await page.goto(
                website_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            result = await observe_page(page)

            print("\n========== WEBSITE INFORMATION ==========")
            print("URL:", result.get("url", "N/A"))
            print("Title:", result.get("title", "N/A"))
            print("Total Elements:", result.get("totalElements", 0))

            print("\n========== DISCOVERED ELEMENTS ==========")

            for element in result.get("elements", []):
                print("\n------------------------")
                print("Reference:", element.get("ref"))
                print("Tag:", element.get("tag"))
                print("Role:", element.get("role"))
                print("Label:", element.get("label"))
                print("Placeholder:", element.get("placeholder"))
                print("Text:", element.get("text"))
                print("Parent Text:", element.get("parentText"))
                print("Required:", element.get("required"))
                print("Disabled:", element.get("disabled"))

            print("\nWebsite observation completed.")
            input("\nPress Enter to close the browser...")

        except Exception as error:
            print(f"\nError: {error}")

        finally:
            if browser:
                await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
