import argparse
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "https://www.samco.in/bhavcopy-nse-bse-mcx"


def download_bhavcopy(
    target_session: date,
    headless: bool = False,
) -> Path:
    session = target_session.isoformat()
    output_dir = Path("data/downloads") / session
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(30_000)

        try:
            page.goto(URL, wait_until="domcontentloaded")

            # Request one session.
            page.locator("#start_date").fill(session)
            page.locator("#end_date").fill(session)

            # Select NSE only. These checkboxes use visible labels.
            for checkbox_id, wanted in [
                ("bhavcopy_data1", True),   # NSE
                ("bhavcopy_data2", False),  # NSEFO
                ("bhavcopy_data3", False),  # BSE
                ("bhavcopy_data4", False),  # MCX
            ]:
                checkbox = page.locator(f"#{checkbox_id}")

                if checkbox.is_checked() != wanted:
                    page.locator(
                        f'label[for="{checkbox_id}"]'
                    ).click()

                if checkbox.is_checked() != wanted:
                    raise RuntimeError(
                        f"Could not set checkbox {checkbox_id}"
                    )

            page.locator("#Show").click()

            # Wait for the requested file to appear before downloading.
            expected_file = f"{target_session:%Y%m%d}_NSE.csv"
            page.get_by_text(
                expected_file, exact=False
            ).first.wait_for(state="visible")

            with page.expect_download(timeout=60_000) as download_info:
                page.locator("#btn_sub").click()

            download = download_info.value
            destination = output_dir / Path(
                download.suggested_filename
            ).name

            download.save_as(destination)

            if destination.stat().st_size == 0:
                raise RuntimeError("Downloaded file is empty")

            print(f"Downloaded: {destination}")
            return destination

        except Exception:
            screenshot = output_dir / "download_error.png"
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"Browser screenshot saved: {screenshot}")
            raise

        finally:
            context.close()
            browser.close()

