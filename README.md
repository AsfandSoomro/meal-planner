# 🤖 Meal Planner Agent

## 🌟 Project Overview
The **Meal Planner Agent** is a Capstone Project for the Kaggle x Google Agentic AI Course.

The primary goal is to solve the daily decision fatigue of meal planning by automating the process using a **Sequential Multi-Agent System** grounded in real-world data.

It suggests a single, optimal lunch meal daily by analyzing fresh inventory from a Google Sheet and checking historical data for variety.

## ✨ Key Agentic Features
This project demonstrates the core concepts of Agentic AI:

* **Sequential Multi-Agent Workflow:** Decomposed into three specialized agents:
    * **Kitchen Manager:** Fetches and synthesizes data.
    * **Creative Chef:** Generates constrained meal options.
    * **Decision Maker:** Selects the best option and notifies.
* **Custom Tools:** Integration with the **Google Sheets API** to access real-time grocery expense data for inventory management.
* **Persistent Memory:** Uses a local JSON-based **Memory Bank** to store family preferences and track meals suggested in the past 14 days, ensuring variety.
* **Action Output:** Uses a **Discord Webhook** tool to push the final, actionable plan directly to the user.

## ⚙️ Setup and Installation

### Prerequisites

1.  **Google Gemini API Key** and necessary Google Cloud setup (Service Account JSON file named `service_account.json`).
2.  **Discord Webhook URL** for notifications.

### Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/AsfandSoomro/meal-planner.git
    cd meal-planner
    ```

2.  **Install Dependencies:**
    ```bash
    uv sync
    ```

3.  **Configure Environment:**
    Create a file named **`.env`** and fill in your details:
    ```env
    GEMINI_API_KEY=your_gemini_key_here
    DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
    GOOGLE_SHEET_ID=your_google_sheet_id_here
    GOOGLE_SHEET_RANGE=Sheet1!A:K 
    ```

## ▶️ How to Run

Execute the main script:

```bash
python main.py