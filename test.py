import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI(title="Stream Extractor Web App")

AD_KEYWORDS = (
    "doubleclick", "googlesyndication", "popads", "propeller",
    "adsterra", "exoclick", "onclick", "trafficjunky", "analytics"
)

SKIP_WORDS = ("sample", "trailer", "promo", "preview", "teaser")


class ExtractRequest(BaseModel):
    url: str


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_sample_link(locator) -> bool:
    try:
        text = (locator.inner_text(timeout=1000) or "").strip().lower()
        href = (locator.get_attribute("href", timeout=1000) or "").strip().lower()
        combined = f"{text} {href}"
        return any(bad in combined for bad in SKIP_WORDS)
    except Exception:
        return False


def click_non_sample_match(active_page, selector: str) -> bool:
    matches = active_page.locator(selector)
    count = matches.count()

    for i in range(count):
        item = matches.nth(i)
        try:
            if not item.is_visible():
                continue
            if is_sample_link(item):
                continue
            item.click(timeout=3000)
            return True
        except Exception:
            continue

    return False


def get_stream_from_movie_url(movie_url: str) -> str | None:
    found_stream_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
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
            page.goto(movie_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            for _ in range(6):
                if found_stream_url:
                    break

                active_page = context.pages[-1]

                if active_page.locator("video").count() > 0:
                    try:
                        active_page.locator("video").first.click(timeout=3000)
                        active_page.wait_for_timeout(4000)
                        if found_stream_url:
                            break
                    except Exception:
                        pass

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

        finally:
            browser.close()

    return found_stream_url


HTML_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Stream Extractor</title>
  <style>
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      justify-content: center;
      padding: 40px 16px;
      margin: 0;
    }
    .card {
      background: #1e293b;
      padding: 24px;
      border-radius: 12px;
      width: 100%;
      max-width: 680px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    }
    h2 { margin-top: 0; }
    .row { display: flex; gap: 10px; margin-bottom: 16px; }
    input {
      flex: 1;
      padding: 12px;
      border-radius: 8px;
      border: 1px solid #334155;
      background: #0f172a;
      color: #fff;
      font-size: 15px;
    }
    button {
      padding: 12px 18px;
      border: none;
      border-radius: 8px;
      background: #3b82f6;
      color: white;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .result {
      display: none;
      background: #0f172a;
      padding: 14px;
      border-radius: 8px;
      border: 1px solid #334155;
      margin-top: 16px;
    }
    .link-box {
      word-break: break-all;
      color: #38bdf8;
      font-size: 14px;
      margin-bottom: 12px;
    }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; }
    .copy-btn { background: #10b981; }
    .open-btn { background: #6366f1; text-decoration: none; color: white; padding: 12px 18px; border-radius: 8px; font-weight: 600; font-size: 14px; }
    video { width: 100%; margin-top: 16px; border-radius: 8px; background: #000; display: none; }
    .status { color: #94a3b8; font-size: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>🎬 Stream URL Extractor</h2>
    <div class="row">
      <input id="urlInput" type="url" placeholder="Paste movie or video page URL (https://...)" />
      <button id="extractBtn" onclick="extractStream()">Extract</button>
    </div>
    <div id="status" class="status"></div>

    <div id="resultBox" class="result">
      <div id="streamLink" class="link-box"></div>
      <div class="actions">
        <button class="copy-btn" onclick="copyLink()">Copy Link</button>
        <a id="openTab" class="open-btn" target="_blank" rel="noopener">Open in New Tab</a>
        <button onclick="playHere()">Play Here</button>
      </div>
    </div>

    <video id="player" controls playsinline></video>
  </div>

  <script>
    let currentStream = "";

    async function extractStream() {
      const url = document.getElementById("urlInput").value.trim();
      const btn = document.getElementById("extractBtn");
      const status = document.getElementById("status");
      const resultBox = document.getElementById("resultBox");
      const player = document.getElementById("player");

      if (!url) return;

      btn.disabled = true;
      resultBox.style.display = "none";
      player.style.display = "none";
      player.pause();
      status.textContent = "⏳ Extracting stream URL... (10-20 seconds aagalaam)";

      try {
        const res = await fetch("/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();

        if (!res.ok) {
          status.textContent = "❌ " + (data.detail || "Extraction failed");
        } else {
          currentStream = data.stream_url;
          document.getElementById("streamLink").textContent = currentStream;
          document.getElementById("openTab").href = currentStream;
          resultBox.style.display = "block";
          status.textContent = "✅ Stream URL kidaichiduchu!";
        }
      } catch (err) {
        status.textContent = "⚠️ Network error: " + err.message;
      } finally {
        btn.disabled = false;
      }
    }

    function copyLink() {
      navigator.clipboard.writeText(currentStream);
      document.getElementById("status").textContent = "📋 Link copied! Browser tab or VLC-la paste pannunga.";
    }

    function playHere() {
      const player = document.getElementById("player");
      player.src = currentStream;
      player.style.display = "block";
      player.play();
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_UI


@app.post("/extract")
async def extract_endpoint(payload: ExtractRequest):
    if not is_valid_url(payload.url):
        raise HTTPException(status_code=400, detail="Sariyaana URL kudunga (https://...)")

    stream_url = await asyncio.to_thread(get_stream_from_movie_url, payload.url)
    if not stream_url:
        raise HTTPException(status_code=404, detail="Original Stream URL kidaikkala.")

    return {"stream_url": stream_url}
