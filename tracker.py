#!/usr/bin/env python3
"""
24/7 Automated Multi-Site Price Drop Tracker with Playwright Support
Monitors product prices across different websites using headless Chromium (Playwright)
and standard HTTP fallback. Compares prices and alerts via Telegram/Discord/Email.
"""

import json
import os
import re
import smtplib
import subprocess
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any, List


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_with_playwright(url: str) -> Optional[int]:
    """Uses Playwright Chromium to bypass Cloudflare/Akamai and render dynamic JavaScript."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
                timezone_id="Asia/Kolkata"
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3500)  # Allow React/Next.js hydration

            domain = urllib.parse.urlparse(url).netloc.lower()
            price = None

            # 1. Amazon
            if "amazon" in domain:
                el = page.query_selector(".a-price-whole")
                if el:
                    cleaned = re.sub(r"[^\d]", "", el.inner_text())
                    if cleaned:
                        price = int(cleaned)

            # 2. Flipkart
            elif "flipkart" in domain:
                for sel in [".Nx9bqj", "._30jeq3", "div._25b18c > div", "[class*='price']"]:
                    el = page.query_selector(sel)
                    if el:
                        cleaned = re.sub(r"[^\d]", "", el.inner_text())
                        if cleaned and int(cleaned) > 500:
                            price = int(cleaned)
                            break

            # 3. Wakefit Official
            elif "wakefit" in domain:
                for sel in [".special-price", ".selling-price", ".final-price", "[data-price]", "span.price"]:
                    el = page.query_selector(sel)
                    if el:
                        cleaned = re.sub(r"[^\d]", "", el.inner_text())
                        if cleaned and int(cleaned) > 500:
                            price = int(cleaned)
                            break

            # 4. Fallback: Parse rendered HTML
            if not price:
                content = page.content()
                price = extract_price(url, content)

            browser.close()
            return price
    except Exception as e:
        print(f"Playwright fetch error for {url}: {e}", file=sys.stderr)
        return None


def fetch_html(url: str) -> str:
    """Fetches web page HTML using curl with realistic headers."""
    if not url:
        return ""
    cmd = [
        "curl", "-s", "-L",
        "-A", USER_AGENT,
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "--max-time", "20",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return ""


def extract_price(url: str, html: str) -> Optional[int]:
    """Extracts selling price from e-commerce page HTML."""
    if not html:
        return None

    domain = urllib.parse.urlparse(url).netloc.lower()

    # 1. Amazon pattern
    if "amazon" in domain:
        matches = re.findall(r'<span class="a-price-whole">([0-9,]+)', html)
        if matches:
            cleaned = matches[0].replace(",", "").replace(".", "").strip()
            if cleaned.isdigit():
                return int(cleaned)

    # 2. Flipkart pattern
    if "flipkart" in domain:
        matches = re.findall(r'₹([0-9,]+)', html)
        if matches:
            for m in matches:
                cleaned = m.replace(",", "").strip()
                if cleaned.isdigit() and int(cleaned) > 500:
                    return int(cleaned)

    # 3. JSON-LD schema price
    schema_matches = re.findall(r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?', html)
    if schema_matches:
        for m in schema_matches:
            val = float(m)
            if val > 100:
                return int(val)

    # 4. Generic Rupee regex fallback
    generic_matches = re.findall(r'(?:₹|Rs\.?|INR)\s*([0-9,]+)', html, re.IGNORECASE)
    if generic_matches:
        for m in generic_matches:
            cleaned = m.replace(",", "").strip()
            if cleaned.isdigit() and int(cleaned) > 100:
                return int(cleaned)

    return None


def send_telegram_alert(bot_token: str, chat_id: str, message: str, plain_text_fallback: str):
    """Sends a Telegram push notification with full error diagnostics and fallback."""
    print(f"\n[Telegram] Delivering alert to Chat ID: {chat_id}...")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("✅ [Telegram] Alert delivered successfully!")
            return
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"⚠️ [Telegram] HTML delivery failed ({e.code}): {err_msg}", file=sys.stderr)
        print("[Telegram] Retrying with plain-text fallback...", file=sys.stderr)

        plain_payload = {
            "chat_id": chat_id,
            "text": plain_text_fallback,
            "disable_web_page_preview": False
        }
        plain_req = urllib.request.Request(
            url,
            data=json.dumps(plain_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(plain_req, timeout=15) as resp:
                print("✅ [Telegram] Plain text alert delivered successfully!")
                return
        except Exception as e2:
            print(f"❌ [Telegram] Retry failed: {e2}", file=sys.stderr)
    except Exception as e:
        print(f"❌ [Telegram] Unexpected error: {e}", file=sys.stderr)


def send_discord_alert(webhook_url: str, title: str, message: str, product_url: str):
    """Sends a rich Discord embed notification."""
    payload = {
        "embeds": [
            {
                "title": f"🚨 {title}",
                "description": message,
                "url": product_url,
                "color": 3066993,  # Green
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("✅ [Discord] Alert delivered successfully!")
    except Exception as e:
        print(f"❌ [Discord] Failed to send alert: {e}", file=sys.stderr)


def send_email_alert(smtp_user: str, smtp_pass: str, to_email: str, subject: str, body: str):
    """Sends an email alert using standard SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #1a73e8; margin-top: 0;">🚨 Price Drop Alert!</h2>
        <p style="font-size: 16px; line-height: 1.5; color: #333;">{body.replace(chr(10), '<br>')}</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #888;">Sent by your 24/7 Automated Price Drop Tracker.</p>
    </div>
    """
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("✅ [Email] Alert sent successfully!")
    except Exception as e:
        print(f"❌ [Email] Failed to send alert: {e}", file=sys.stderr)


def check_product(item: Dict[str, Any]) -> Dict[str, Any]:
    """Checks prices for a single product across all its configured store links."""
    name = item.get("name", "Unknown Product")
    threshold = item.get("threshold_price", 0)
    currency = item.get("currency", "INR")

    stores_list = item.get("stores", [])
    if not stores_list and item.get("url"):
        stores_list = [{"store": "Amazon India", "url": item.get("url")}]

    # Check if Playwright is available in the environment
    try:
        import playwright
        has_playwright = True
    except ImportError:
        has_playwright = False

    store_results = []
    for s in stores_list:
        s_name = s.get("store", "Store")
        s_url = s.get("url", "")
        price = None

        if has_playwright:
            print(f"Fetching from {s_name} with Headless Browser...")
            price = fetch_with_playwright(s_url)

        if not price:
            print(f"Fetching from {s_name} with HTTP...")
            html = fetch_html(s_url)
            price = extract_price(s_url, html)

        if price:
            print(f"  -> {s_name}: {currency} {price:,}")
            store_results.append({"store": s_name, "url": s_url, "price": price})
        else:
            print(f"  -> {s_name}: Price not found")

    if not store_results:
        return {
            "name": name,
            "threshold": threshold,
            "currency": currency,
            "lowest_price": None,
            "lowest_store": None,
            "lowest_url": None,
            "all_stores": [],
            "status": "⚠️ Failed to fetch"
        }

    # Sort stores by price to find the absolute lowest deal
    store_results.sort(key=lambda x: x["price"])
    best = store_results[0]
    is_below = best["price"] <= threshold

    return {
        "name": name,
        "threshold": threshold,
        "currency": currency,
        "lowest_price": best["price"],
        "lowest_store": best["store"],
        "lowest_url": best["url"],
        "all_stores": store_results,
        "status": "✅ Price Below Threshold!" if is_below else "⏳ Above Threshold"
    }


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    products_file = os.path.join(base_dir, "products.json")
    history_file = os.path.join(base_dir, "history.json")

    if not os.path.exists(products_file):
        print(f"Error: {products_file} not found.", file=sys.stderr)
        sys.exit(1)

    with open(products_file, "r") as f:
        products = json.load(f)

    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    tg_chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    discord_webhook = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    email_user = (os.getenv("EMAIL_USER") or "").strip()
    email_pass = (os.getenv("EMAIL_PASS") or "").strip()
    email_to = (os.getenv("EMAIL_TO") or email_user).strip()

    print("=" * 50)
    print("🔔 Notification Configuration:")
    print(f"  Telegram Bot Token: {'Configured ✅' if tg_token else 'NOT SET ❌'}")
    print(f"  Telegram Chat ID:   {'Configured ✅ (' + tg_chat_id + ')' if tg_chat_id else 'NOT SET ❌'}")
    print(f"  Discord Webhook:    {'Configured ✅' if discord_webhook else 'NOT SET'}")
    print(f"  Email Alerts:       {'Configured ✅' if email_user and email_pass else 'NOT SET'}")
    print("=" * 50)

    summary_rows = []
    history = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            history = {}

    print(f"\nChecking {len(products)} product(s)...")

    for item in products:
        name = item.get("name", "Product")
        print(f"\n--- Checking: {name} ---")
        res = check_product(item)

        threshold = res["threshold"]
        currency = res["currency"]
        lowest = res["lowest_price"]
        lowest_store = res["lowest_store"]
        lowest_url = res["lowest_url"]

        if lowest:
            print(f"🏆 Lowest: {currency} {lowest:,} on {lowest_store} | Target: {currency} {threshold:,}")
            summary_rows.append(f"| {name} | **{currency} {lowest:,}** ({lowest_store}) | {currency} {threshold:,} | {res['status']} |")

            if lowest <= threshold:
                savings = threshold - lowest
                savings_str = f" (Savings: {currency} {savings:,})" if savings > 0 else ""

                comparison_lines = []
                for s in res["all_stores"]:
                    marker = "🏆 " if s["store"] == lowest_store else "   "
                    comparison_lines.append(f"{marker}• {s['store']}: {currency} {s['price']:,}")
                comparison_text = "\n".join(comparison_lines)

                tg_html_msg = (
                    f"🚨 <b>PRICE DROP ALERT!</b>\n\n"
                    f"<b>{name}</b> is now at the lowest price!\n\n"
                    f"🏆 <b>Lowest Store:</b> {lowest_store}\n"
                    f"💰 <b>Current Price:</b> {currency} {lowest:,}{savings_str}\n"
                    f"🎯 <b>Target Threshold:</b> {currency} {threshold:,}\n\n"
                    f"📊 <b>Cross-Site Comparison:</b>\n{comparison_text}\n\n"
                    f"👉 <a href=\"{lowest_url}\">Click Here to Buy on {lowest_store}</a>"
                )

                tg_plain_msg = (
                    f"🚨 PRICE DROP ALERT!\n\n"
                    f"{name} is now at the lowest price!\n\n"
                    f"Lowest Store: {lowest_store}\n"
                    f"Current Price: {currency} {lowest:,}{savings_str}\n"
                    f"Target Threshold: {currency} {threshold:,}\n\n"
                    f"Cross-Site Comparison:\n{comparison_text}\n\n"
                    f"Buy link: {lowest_url}"
                )

                print(">>> ALERT CONDITION MET! Dispatching notifications...")

                if tg_token and tg_chat_id:
                    send_telegram_alert(tg_token, tg_chat_id, tg_html_msg, tg_plain_msg)

                if discord_webhook:
                    send_discord_alert(discord_webhook, f"Price Drop: {name}", tg_plain_msg, lowest_url)

                if email_user and email_pass and email_to:
                    send_email_alert(email_user, email_pass, email_to, f"Price Drop: {name}", tg_plain_msg)

                if sys.platform == "darwin":
                    msg = f"Lowest: {currency} {lowest:,} on {lowest_store}!"
                    subprocess.run([
                        "osascript", "-e",
                        f'display notification "{msg}" with title "Price Drop Alert" sound name "Glass"'
                    ], check=False)

            history[name] = {
                "lowest_price": lowest,
                "lowest_store": lowest_store,
                "lowest_url": lowest_url,
                "threshold": threshold,
                "currency": currency,
                "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            summary_rows.append(f"| {name} | Unknown | {currency} {threshold:,} | ⚠️ Failed to fetch |")

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)

    gh_summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if gh_summary_path:
        with open(gh_summary_path, "a") as f:
            f.write("### 🏷️ Multi-Site Price Tracker Summary\n\n")
            f.write(f"*Check completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*\n\n")
            f.write("| Product | Lowest Price Found | Target Threshold | Status |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for row in summary_rows:
                f.write(f"{row}\n")
            f.write("\n")


if __name__ == "__main__":
    main()
