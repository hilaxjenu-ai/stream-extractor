from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

AD_KEYWORDS = (
    "doubleclick", "googlesyndication", "popads", "propeller",
    "adsterra", "exoclick", "onclick", "trafficjunky", "analytics"
)

SKIP_WORDS = ("sample", "trailer", "promo", "preview", "teaser")


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_sample_link(locator) -> bool:
    """Link text or href-la 'sample' / promo words irundha True nu sollum."""
    try:
        text = (locator.inner_text(timeout=1000) or "").strip().lower()
        href = (locator.get_attribute("href", timeout=1000) or "").strip().lower()
        combined = f"{text} {href}"
        return any(bad in combined for bad in SKIP_WORDS)
    except Exception:
        return False


def click_non_sample_match(active_page, selector: str) -> bool:
    """Selector-kku match aagura links-la sample illadha first visible link-a click pannum."""
    matches = active_page.locator(selector)
    count = matches.count()

    for i in range(count):
        item = matches.nth(i)
        try:
            if not item.is_visible():
                continue
            if is_sample_link(item):
                print(f"   ⏭️ Skipping sample/promo link ({selector} [{i}])")
                continue

            label = (item.inner_text(timeout=1000) or "").strip()
            print(f"   -> Clicking non-sample link: '{label or selector}'")
            item.click(timeout=3000)
            return True
        except Exception:
            continue

    return False


def get_stream_from_movie_url(movie_url: str, headless: bool = False) -> str | None:
    """Sample-a skip panni original / main stream URL edukkum."""
    found_stream_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )

        def block_ads(route):
            req_url = route.request.url.lower()
            if any(bad in req_url for bad in AD_KEYWORDS):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", block_ads)

        def handle_response(response):
            nonlocal found_stream_url
            if found_stream_url is not None:
                return

            res_url = response.url
            res_lower = res_url.lower()
            headers = {k.lower(): v.lower() for k, v in response.headers.items()}
            ctype = headers.get("content-type", "")
            cdisp = headers.get("content-disposition", "")

            # Sample stream URL-a avoid panna try panrom
            if "sample" in res_lower or "sample" in cdisp:
                return

            if (
                ".mp4" in res_lower
                or ".m3u8" in res_lower
                or ".mpd" in res_lower
                or "video/" in ctype
                or "mpegurl" in ctype
                or "mp4" in cdisp
            ):
                found_stream_url = res_url

        context.on("response", handle_response)
        page = context.new_page()

        try:
            print(f"⏳ Loading URL: {movie_url}")
            page.goto(movie_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            for step in range(6):
                if found_stream_url:
                    break

                active_page = context.pages[-1]
                print(f"   Step {step + 1}: {active_page.url}")

                if active_page.locator("video").count() > 0:
                    try:
                        active_page.locator("video").first.click(timeout=3000)
                        active_page.wait_for_timeout(4000)
                        if found_stream_url:
                            break
                    except Exception:
                        pass

                # 'Original' / 'Full' links-a first priority-la vekkurom
                selectors = [
                    "a:has-text('Original')",
                    "a:has-text('Full')",
                    "a[href*='original']",
                    "a[href*='stream']",
                    "a[href*='watch']",
                    "a[href*='download']",
                    "a:has-text('640x360')",
                    "a:has-text('720p')",
                    "a:has-text('480p')",
                    "a:has-text('HD')",
                    "a:has-text('Watch')",
                    "a:has-text('Stream')",
                    "a:has-text('Download')",
                    "a:has-text('Server')",
                ]

                clicked = False
                for sel in selectors:
                    if click_non_sample_match(active_page, sel):
                        active_page.wait_for_timeout(3000)
                        clicked = True
                        break

                if not clicked:
                    active_page.wait_for_timeout(2000)

        except Exception as e:
            print(f"⚠️ Error: {e}")
        finally:
            browser.close()

    return found_stream_url


def main():
    while True:
        user_url = input("\nMovie / Video Page URL enter pannunga (exit nu type panna veliya varalaam): ").strip()
        if not user_url:
            continue
        if user_url.lower() == "exit":
            print("Bye! App project-kku best of luck.")
            break

        if not is_valid_url(user_url):
            print("❌ Sariyaana URL kudunga (https://...)")
            continue

        stream_url = get_stream_from_movie_url(user_url, headless=True)

        if stream_url:
            print("\n🎉 Original Stream URL:")
            print(stream_url)
        else:
            print("\n⚠️ Original Stream URL kidaikkala.")


if __name__ == "__main__":
    main()