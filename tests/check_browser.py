"""Offline Chromium smoke tests for the current static demo, not a production audit."""
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

def scenario(page):
    page.locator("#photos img").first.click()
    expect(page.locator("#viewer")).to_be_visible()
    before = page.locator("#count").inner_text()
    page.locator("#next").click()
    expect(page.locator("#count")).not_to_have_text(before)
    page.locator("#close").click()
    expect(page.locator("#viewer")).not_to_be_visible()
    page.locator("#check").click()
    expect(page.locator("#status")).to_contain_text("Укажите корректные даты")
    arrival = date.today() + timedelta(days=30)
    page.locator("#arrival").fill(arrival.isoformat())
    page.locator("#departure").fill(arrival.isoformat())
    page.locator("#check").click()
    expect(page.locator("#status")).to_contain_text("Укажите корректные даты")
    page.locator("#departure").fill((arrival + timedelta(days=2)).isoformat())
    page.locator("#check").click()
    expect(page.locator("#status")).to_contain_text("календарь не подключён")

def main():
    # Bind to loopback only. Test the checked-out files, never a live site.
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for label, viewport in (("desktop", {"width": 1440, "height": 900}),
                                    ("mobile viewport", {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport, service_workers="block")
                page = context.new_page()
                errors = []
                failed_local = []
                unexpected = []
                def route_request(route):
                    url = urlsplit(route.request.url)
                    if f"{url.scheme}://{url.netloc}" == origin and route.request.method in ("GET", "HEAD"):
                        route.continue_()
                    else:
                        if route.request.method not in ("GET", "HEAD"):
                            unexpected.append(route.request.method)
                        route.abort()
                context.route("**/*", route_request)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: failed_local.append(response.status)
                        if response.url.startswith(origin + "/") and response.status >= 400
                        and not response.url.endswith("/favicon.ico") else None)
                try:
                    response = page.goto(origin + "/index.html", wait_until="load")
                    assert response and response.ok
                    expect(page.locator("h1").first).to_be_visible()
                    scenario(page)
                    assert not errors, errors
                    assert not failed_local, failed_local
                    assert not unexpected, unexpected
                    print(f"PASS: {label}")
                finally:
                    context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

if __name__ == "__main__":
    main()
