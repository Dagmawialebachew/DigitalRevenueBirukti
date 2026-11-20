# 🏋️‍♀️ Biruktawit Fikre (@gibdaw) — Workout-Plan Telegram Bot

A clean, modular, and decoupled Telegram bot platform built specifically to sell and deliver **Biruktawit Fikre's** structured 8-Week Workout Programs.

---

## 🌟 Key Features

1. **Addis-Native Gym Localization:** Authentic Addis Ababa Amharic with natural fitness English loanwords (*Workout, Gym, Form, Booty, Sets, Reps*). Zero robotic AI jargon.
2. **Deep Intake Personalization:** Captures **Gender**, **Age**, **Weight (kg)**, **Goal**, **Frequency (3x/4x)**, and **Experience Level**.
3. **Instant Free Value Drop:** Delivers the Free Lifting & Form Primer PDF immediately after the personalized diagnostic card without asking for pledge or commitment buttons.
4. **Clean 4-Table Database:** Operates with four standalone tables (`athletes`, `workout_catalog`, `orders`, `payout_ledger`).
5. **Dynamic 60/40 ➔ 70/30 Revenue Split:** 
   - Sales 1–150: 60% Creator / 40% Platform
   - Sales 151+: 70% Creator / 30% Platform permanently
6. **Anti-Fingerprint Disguise:** Custom client IDs (`BF-XXXX`), distinct visual styles, and zero resemblance to Coach Hilawe's platform.

---

## 📁 Project Structure

```text
DigitalRevenueBiruktawit/
├── bot.py                  # Bot entry point & lifecycle manager
├── config.py               # Pydantic settings loading from .env
├── requirements.txt        # Minimal, lean dependencies
├── database/
│   ├── db.py               # AsyncPG connection pool & helper queries
│   └── schema.sql          # 4-table schema & catalog seeding
├── handlers/
│   ├── onboarding.py       # Funnel, diagnostic card & free value drop
│   ├── payment.py          # Receipt screenshot submission
│   └── admin.py            # One-click approvals & /payouts dashboard
├── services/
│   ├── payout_engine.py    # 60/40 -> 70/30 immutable ledger logic
│   ├── verifier.py         # Anti-replay & Biruktawit recipient validator
│   └── deliverer.py        # PDF dispatcher
└── static/
    ├── images/             # welcome_biruktawit.jpg
    └── pdfs/               # Primer guide & 12 workout PDFs
```

---

## 🚀 Setup & Launch

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your BOT_TOKEN, DATABASE_URL, and Bank Details
   ```

3. **Add Assets:**
   - Place Biruktawit's welcome photo at `static/images/welcome_biruktawit.jpg`.
   - Place the free foundation PDF at `static/pdfs/Biruktawit_Fitness_Foundation_Guide.pdf`.
   - Place the 12 workout program PDFs in `static/pdfs/`.

4. **Start the Bot:**
   ```bash
   python bot.py
   ```

