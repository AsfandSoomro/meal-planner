import os
import json
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.adk.agents import Agent, SequentialAgent
from google.adk.model import Model
from discord_webhook import DiscordWebhook

# 1. Load Environment Variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "Sheet1!A:K")
SERVICE_ACCOUNT_FILE = 'service_account.json'

# Initialize Model
model = Model(model="gemini-2.5-flash", api_key=GEMINI_API_KEY)

# --- REAL Tool Definitions ---

def fetch_recent_grocery_data():
    """
    Connects to the real Google Sheet, downloads the data, and filters
    for items bought in the last 14 days to find available inventory.
    """
    print(f"📊 Connecting to Google Sheet ID: {SPREADSHEET_ID}...")
    
    # Authenticate with Google Sheets
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, 
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    service = build('sheets', 'v4', credentials=creds)

    # Fetch Data
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE).execute()
    values = result.get('values', [])

    if not values:
        return "No data found in the spreadsheet."

    # Convert to DataFrame using your specific columns
    # We assume the first row in 'values' contains headers, but we force your names just in case
    expected_cols = ["DATE", "ITEM", "STORE", "CATEGORY", "QTY", "UNIT", "PRICE", "COMMENT", "DAY", "MONTH", "YEAR"]
    
    # If the sheet has headers, skip row 0, else use all. 
    # Adjust logic if your sheet starts data at row 2.
    df = pd.DataFrame(values[1:], columns=expected_cols)

    # Data Cleaning & Date Parsing
    # Assuming DATE is in a standard format (e.g., YYYY-MM-DD or DD/MM/YYYY)
    df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce') 
    
    # Filter: Last 14 Days
    two_weeks_ago = datetime.now() - timedelta(days=14)
    recent_items = df[df['DATE'] >= two_weeks_ago]

    # Filter: Vegetables Only (Adjust 'Vegetable' to match your exact CATEGORY text)
    # We use string contains to be safe (e.g. "Vegetables", "Veggies", "Fresh Vegetables")
    veggies = recent_items[recent_items['CATEGORY'].astype(str).str.contains("Veg", case=False, na=False)]

    # Convert to a readable list for the Agent
    inventory_list = []
    for _, row in veggies.iterrows():
        inventory_list.append(f"{row['ITEM']} ({row['QTY']} {row['UNIT']}) bought on {row['DATE'].strftime('%Y-%m-%d')}")

    if not inventory_list:
        return "No vegetables found bought in the last 14 days. Check if 'CATEGORY' column matches 'Veg'."

    return "\n".join(inventory_list)

def read_memory_bank():
    """Reads the local JSON memory bank for family preferences and history."""
    try:
        with open("memory_bank.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # Default structure if file doesn't exist
        return {
            "dislikes": [], 
            "favorites": ["Daal Chawal", "Chicken Handi White"], 
            "last_14_days_suggestions": [] 
        }

def send_discord_notification(message: str):
    """Sends the final meal plan to Discord."""
    print("📨 Sending notification to Discord...")
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
    response = webhook.execute()
    return f"Notification sent. Status: {response.status_code}"

# --- Agents & Prompts ---

# 1. Data Agent
data_agent_prompt = """
You are the **Inventory & Context Manager**.
Your goal is to inspect the real grocery data and preparation history.

1. **Get Real Inventory:** Call `fetch_recent_grocery_data` to see what was bought recently.
2. **Check Memory:** Call `read_memory_bank` to see what was suggested in the last 2 weeks to avoid repeats.
3. **Report:** Output a 'Kitchen State' summary.
   - List the AVAILABLE VEGETABLES based on the tool output.
   - List the FORBIDDEN MEALS (those suggested in the last 2 weeks).
"""

data_agent = Agent(
    name="KitchenManager",
    model=model,
    instruction=data_agent_prompt,
    tools=[fetch_recent_grocery_data, read_memory_bank]
)

# 2. Planner Agent
planner_agent_prompt = """
You are the **Creative Chef**.
Receive the 'Kitchen State' from the Kitchen Manager.

Your goal is to generate **3 distinct Lunch Options**.

**Constraint Checklist:**
1. MUST use at least one 'Available Vegetable' listed.
2. MUST NOT be a 'Forbidden Meal' (recently eaten).
3. If the user has 'Favorites' in memory that match the ingredients, prioritize one of them.

Output format:
1. [Meal Name] - [Main Veggie] - [Reason]
2. [Meal Name] - ...
3. [Meal Name] - ...
"""

planner_agent = Agent(
    name="CreativeChef",
    model=model,
    instruction=planner_agent_prompt
)

# 3. Selection Agent
selection_agent_prompt = """
You are the **Final Decision Maker**.
Pick the SINGLE best lunch option from the Chef's list.

**Action:**
1. Choose the meal that uses the most perishable ingredient or is a family favorite.
2. Use `send_discord_notification` to send the final decision.
3. **Crucial:** You must format the message beautifully for Discord (use bolding and emojis).
"""

selection_agent = Agent(
    name="DecisionMaker",
    model=model,
    instruction=selection_agent_prompt,
    tools=[send_discord_notification]
)

# --- Workflow Execution ---

def run_meal_planner():
    print("🚀 Starting Agentic Meal Planner...")
    
    # Sequential Workflow
    workflow = SequentialAgent(
        agents=[data_agent, planner_agent, selection_agent]
    )
    
    # Run
    result = workflow.run("Check the fridge and plan tomorrow's lunch.")
    print("✅ Process Complete.")
    return result

if __name__ == "__main__":
    run_meal_planner()
