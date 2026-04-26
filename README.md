# ✈️ FlyTrade

![Status](https://img.shields.io/badge/Status-In%20Development-yellow)
![License](https://img.shields.io/badge/License-MIT-green)
![Python](https://img.shields.io/badge/Python-3.9+-blue)

**FlyTrade** is a Telegram bot paired with a web-based administrative panel, developed using FastAPI and SQLAlchemy. The project's main goal is to streamline the negotiation (buying and selling) of airline miles (such as SMILES, LATAM, QATAR, etc.) in an intuitive way, connecting buyers and sellers through a structured system of offers, counter-offers, and ratings.

---

### 🇧🇷 Language Note

All user-facing text, including bot messages and web interfaces, is written entirely in **Brazilian Portuguese**.

---

## ⚠️ Important Notice

This is a **personal project** developed purely as a **hobby** in my spare time. As it is under continuous development and not a finished product:
- 🐛 **There are bugs:** You will most likely encounter errors or incomplete workflows.
- 🚧 **Missing features:** Several functionalities may be pending or implemented in a rudimentary way.
- 🛠️ **No guarantees:** Use at your own risk in production environments.

## 🔓 License and Use

The code in this repository is **completely open**. Feel free to:
- Clone, copy, and modify.
- Use it for study or personal projects.
- Commercialize or integrate it into your own systems.
Do whatever you want with the files! There are no strict copyright restrictions.

---

## 🛠️ What does the project do?

Currently, FlyTrade allows:
- **Buy/Sell Listings:** Users can post offers for miles on specific Telegram channels.
- **Negotiation System:** Buttons integrated into the listings allow interested parties to send proposals and counter-proposals.
- **Profiles & Reputation:** A mini Web Application (WebApp) within Telegram to view trader profiles, showing the amount of miles traded and a rating system (1 to 5 stars) with comments.
- **Admin Panel:** A web dashboard (FastAPI) to monitor metrics and manage mileage programs and their banners.

## 🚀 How to Run (Basic)

1. Clone the repository.
2. Create a virtual environment and install the dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Rename `.env.example` to `.env` and fill in your credentials.
4. Run the application (Bot + Web):
   ```bash
   PYTHONPATH=. python3 main.py
   ```

---

*The only documentation is `git blame`. Good luck*
