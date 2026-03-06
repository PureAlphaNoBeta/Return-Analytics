from playwright.sync_api import sync_playwright
import time

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:8501")

    # Wait for the app to load
    page.wait_for_selector("text=Performance Analytics", timeout=10000)
    time.sleep(2)

    # Upload the new dummy file
    file_input = page.locator("input[type='file']")
    file_input.set_input_files("dummy_multi_fund_data.xlsx")

    # Wait for upload to process
    time.sleep(5)

    # Check if there is a multi select dropdown
    page.screenshot(path="debug_upload.png", full_page=True)

    # Try finding the multiselect via its label text again or just look at debug image
    page.get_by_text("Select Funds to Analyze").wait_for(timeout=10000)

    # Use standard multiselect logic
    multiselect = page.locator("div[data-testid='stMultiSelect']").first
    multiselect.click()
    page.locator("li[role='option']", has_text="Fund A").click()
    time.sleep(1)

    multiselect.click()
    page.locator("li[role='option']", has_text="Fund B").click()
    time.sleep(2)

    # Click on the Exposures tab
    page.get_by_role("tab", name="Exposures").click()
    time.sleep(3) # Wait for chart to render

    # Take screenshot of the exposures tab
    page.screenshot(path="tab_exposures_multi_fund.png", full_page=True)
    print("Screenshot saved to tab_exposures_multi_fund.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
