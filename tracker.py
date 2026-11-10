#!/usr/bin/env python3
"""
24/7 Automated Price Drop Tracker
Monitors product prices and triggers alerts when prices drop below defined thresholds.
Runs locally or on GitHub Actions (100% free).
"""

import json
import os
import re
import smtplib
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    """Fetches web page HTML using curl with realistic headers."""
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


from typing import Optional

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

    # 3. Generic JSON-LD schema price
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
            print("Discord alert sent successfully!")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}", file=sys.stderr)


def send_telegram_alert(bot_token: str, chat_id: str, message: str):
    """Sends a Telegram push notification."""
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("Telegram alert sent successfully!")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}", file=sys.stderr)


def send_email_alert(smtp_user: str, smtp_pass: str, to_email: str, subject: str, body: str):
    """Sends an email alert using standard SMTP (e.g. Gmail App Password)."""
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
        print("Email alert sent successfully!")
    except Exception as e:
        print(f"Failed to send email alert: {e}", file=sys.stderr)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    products_file = os.path.join(base_dir, "products.json")
    history_file = os.path.join(base_dir, "history.json")

    if not os.path.exists(products_file):
        print(f"Error: {products_file} not found.", file=sys.stderr)
        sys.exit(1)

    with open(products_file, "r") as f:
        products = json.load(f)

    history = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            history = {}

    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    email_to = os.getenv("EMAIL_TO") or email_user

    summary_rows = []
    print(f"Checking {len(products)} product(s)...")

    for item in products:
        name = item.get("name", "Unknown Product")
        url = item.get("url", "")
        threshold = item.get("threshold_price", 0)
        currency = item.get("currency", "INR")

        print(f"\n--- Checking: {name} ---")
        html = fetch_html(url)
        current_price = extract_price(url, html)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if current_price:
            print(f"Current Price: {currency} {current_price:,} | Threshold: {currency} {threshold:,}")
            status = "✅ Price Below Threshold!" if current_price <= threshold else "⏳ Above Threshold"
            summary_rows.append(f"| {name} | {currency} {current_price:,} | {currency} {threshold:,} | {status} |")

            # Check if alert condition met
            if current_price <= threshold:
                alert_title = f"Price Drop Alert: {name}"
                savings = threshold - current_price
                savings_text = f" (Savings: {currency} {savings:,})" if savings > 0 else ""
                
                alert_text = (
                    f"<b>{name}</b> is now available for <b>{currency} {current_price:,}</b>!{savings_text}\n"
                    f"Target Threshold: {currency} {threshold:,}\n\n"
                    f"👉 <a href='{url}'>Click Here to Buy Now</a>"
                )

                print(">>> ALERT TRIGGERED! Sending notifications...")

                # 1. Discord
                if discord_webhook:
                    send_discord_alert(discord_webhook, alert_title, alert_text, url)

                # 2. Telegram
                if tg_token and tg_chat_id:
                    send_telegram_alert(tg_token, tg_chat_id, alert_text)

                # 3. Email
                if email_user and email_pass and email_to:
                    send_email_alert(email_user, email_pass, email_to, alert_title, alert_text)

                # 4. Local macOS notification (if running on Mac)
                if sys.platform == "darwin":
                    msg = f"Now {currency} {current_price:,} (below threshold {currency} {threshold:,})"
                    subprocess.run([
                        "osascript", "-e",
                        f'display notification "{msg}" with title "Price Drop: {name}" sound name "Glass"'
                    ], check=False)

            # Update history
            history[url] = {
                "name": name,
                "last_price": current_price,
                "threshold": threshold,
                "currency": currency,
                "last_checked": timestamp
            }
        else:
            print("Could not extract price (page structure may have changed or blocked).")
            summary_rows.append(f"| {name} | Unknown | {currency} {threshold:,} | ⚠️ Failed to fetch |")

    # Save history
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)

    # Write GitHub Step Summary if running in GitHub Actions
    gh_summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if gh_summary_path:
        with open(gh_summary_path, "a") as f:
            f.write("### 🏷️ Price Tracker Run Summary\n\n")
            f.write(f"*Run completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*\n\n")
            f.write("| Product | Current Price | Target Threshold | Status |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for row in summary_rows:
                f.write(f"{row}\n")
            f.write("\n")


if __name__ == "__main__":
    main()
