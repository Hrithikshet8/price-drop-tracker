# 🏷️ 24/7 Automated Price Drop Tracker

An automated price tracker powered by GitHub Actions that monitors e-commerce prices 24/7 (even when your computer is asleep or off) and sends instant alerts when a price drops below your target threshold.

## 🚀 Features
- **100% Free**: Uses standard GitHub Actions free tier.
- **24/7 Cloud Monitoring**: Runs every hour without needing your laptop open.
- **Multiple Notification Channels**:
  - **Discord Webhook** (Rich embed alerts)
  - **Telegram Bot** (Push notifications to your phone)
  - **Email** (Via Gmail App Password / SMTP)
  - **macOS Native Banner** (When tested locally)
- **Automatic History**: Updates `history.json` and posts a summary table to GitHub Actions Step Summary.

---

## 📦 Monitored Products
Add or edit tracked items in `products.json`:

```json
[
  {
    "name": "Wakefit Orthopaedic Memory Foam Mattress 6-Inch (Queen 78x60)",
    "url": "https://www.amazon.in/Wakefit-Orthopaedic-Memory-Mattress-6inch/dp/B00RAEVRZQ?th=1",
    "threshold_price": 8400,
    "currency": "INR"
  }
]
```

---

## 🛠️ Quick Setup (Push to Your GitHub)

### 1. Create a New Repository
Go to [github.com/new](https://github.com/new) and create a repository named:
`price-drop-tracker` *(can be Public or Private)*.

### 2. Push this Folder to GitHub
Run these commands in your terminal:

```bash
cd /Users/hrithiksh8/.gemini/antigravity/scratch/price-drop-tracker
git init
git add .
git commit -m "feat: initial price tracker with Wakefit mattress"
git branch -M main
git remote add origin https://github.com/Hrithikshet8/price-drop-tracker.git
git push -u origin main
```

---

## 🔔 Configure Alert Notifications (GitHub Secrets)

Go to your repository on GitHub:
**Settings → Secrets and variables → Actions → New repository secret**

Add any of these secrets depending on where you want alerts:

### Option A: Discord Webhook (Easiest)
1. In Discord: Server Settings → Integrations → Webhooks → Create Webhook → Copy Webhook URL.
2. Add Secret: `DISCORD_WEBHOOK_URL` = `<your webhook URL>`

### Option B: Telegram Bot (Phone Push Alerts)
1. Message `@BotFather` on Telegram to create a bot and get a token.
2. Message `@userinfobot` to get your Chat ID.
3. Add Secrets:
   - `TELEGRAM_BOT_TOKEN` = `<your bot token>`
   - `TELEGRAM_CHAT_ID` = `<your chat id>`

### Option C: Email (Gmail App Password)
1. Generate an [App Password](https://myaccount.google.com/apppasswords).
2. Add Secrets:
   - `EMAIL_USER` = `hrithik356hrithik@gmail.com`
   - `EMAIL_PASS` = `<your 16-character app password>`
   - `EMAIL_TO` = `hrithik356hrithik@gmail.com`

---

## ⏱️ Workflow Schedule
The tracker automatically runs every hour (`cron: '0 * * * *'`).
You can also trigger a run manually at any time by going to the **Actions** tab on GitHub and clicking **Run workflow**.
