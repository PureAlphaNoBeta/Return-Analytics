from playwright.sync_api import sync_playwright

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8501")

        page.wait_for_selector("text=Performance Analytics", timeout=10000)

        page.locator("input[type='file']").set_input_files("dummy_data_v3.xlsx")

        page.wait_for_selector("text=Data successfully uploaded and categorized into the database!", timeout=10000)

        page.wait_for_selector("text=Select Funds to Analyze")

        # Select "Fund A" and "Fund B"
        page.locator("div[data-baseweb='select']").first.click()
        page.wait_for_timeout(1000)
        page.locator("li[role='option']").nth(0).click() # Fund A
        page.wait_for_timeout(1000)

        # 1. Growth & Drawdown
        page.click("button:has-text('Growth & Drawdown')")
        page.wait_for_timeout(3000)
        page.screenshot(path="tab_growth_drawdown.png", full_page=True)

        # 2. Risk & Distribution
        page.click("button:has-text('Risk & Distribution')")
        page.wait_for_timeout(3000)
        page.screenshot(path="tab_risk_distribution.png", full_page=True)

        # 3. Exposures
        page.click("button:has-text('Exposures')")
        page.wait_for_timeout(3000)
        page.screenshot(path="tab_exposures.png", full_page=True)

        browser.close()

if __name__ == "__main__":
    verify()
