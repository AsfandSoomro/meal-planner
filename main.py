import os
import json
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.adk.agents import Agent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types
from discord_webhook import DiscordWebhook
import asyncio

# 1. Load Environment Variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "Sheet1!A:K")
SERVICE_ACCOUNT_FILE = 'service_account.json'

retry_config=types.HttpRetryOptions(
    attempts=5,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504], # Retry on these HTTP errors
)

model = Gemini(model="gemini-2.5-flash", retry_config=retry_config)

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

def write_memory_bank(data: dict):
    """Writes data to the memory bank JSON file."""
    with open("memory_bank.json", "w") as f:
        json.dump(data, f, indent=2)
    return "Memory bank updated successfully."

def update_preferences(favorite: str = None, dislike: str = None):
    """
    Updates family preferences in the memory bank.
    Used by the Planner Agent to store favorites and dislikes.
    
    Args:
        favorite: A meal name to add to favorites (optional)
        dislike: A meal name to add to dislikes (optional)
    """
    memory = read_memory_bank()
    
    if favorite and favorite not in memory.get("favorites", []):
        memory.setdefault("favorites", []).append(favorite)
        print(f"✅ Added '{favorite}' to favorites")
    
    if dislike and dislike not in memory.get("dislikes", []):
        memory.setdefault("dislikes", []).append(dislike)
        print(f"❌ Added '{dislike}' to dislikes")
    
    write_memory_bank(memory)
    return f"Preferences updated. Favorites: {memory.get('favorites', [])}, Dislikes: {memory.get('dislikes', [])}"

def save_selected_meal(meal_name: str):
    """
    Saves the selected meal to the last 14 days suggestions.
    Used by the Selection Agent to track recent meal choices.
    
    Args:
        meal_name: The name of the meal that was selected
    """
    memory = read_memory_bank()
    
    # Add the meal with timestamp
    suggestion_entry = {
        "meal": meal_name,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    
    # Initialize list if it doesn't exist
    if "last_14_days_suggestions" not in memory:
        memory["last_14_days_suggestions"] = []
    
    # Add new suggestion
    memory["last_14_days_suggestions"].append(suggestion_entry)
    
    # Keep only last 14 days (prune old entries)
    cutoff_date = datetime.now() - timedelta(days=14)
    memory["last_14_days_suggestions"] = [
        entry for entry in memory["last_14_days_suggestions"]
        if datetime.strptime(entry["date"], "%Y-%m-%d") >= cutoff_date
    ]
    
    write_memory_bank(memory)
    print(f"💾 Saved '{meal_name}' to meal history")
    return f"Saved '{meal_name}' to last 14 days suggestions."

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
    tools=[fetch_recent_grocery_data, read_memory_bank],
    output_key="kitchen_state",
)

# 2. Planner Agent
planner_agent_prompt = """
You are the **Creative Chef**.
You must generate lunch options based **ONLY** on the following data:
**KITCHEN STATE REPORT:** {kitchen_state}

Your goal is to generate **3 distinct Lunch Options**.

**Constraint Checklist:**
1. MUST use at least one 'Available Vegetable' listed in the report.
2. MUST NOT be a 'Forbidden Meal' listed in the report.
3. If the user has 'Favorites' in memory that match the ingredients, prioritize one of them.
4. OPTIONAL: If you identify a meal that should be added to favorites or dislikes based on patterns, 
   you can use the `update_preferences` tool to save it.

Output format:
1. [Meal Name] - [Main Veggie] - [Reason]
2. [Meal Name] - ...
3. [Meal Name] - ...
"""

planner_agent = Agent(
    name="CreativeChef",
    model=model,
    instruction=planner_agent_prompt,
    tools=[update_preferences],
    output_key="meal_options"
)

# 3. Selection Agent
selection_agent_prompt = """
You are the **Final Decision Maker**.
Review the following meal options and select the single best choice:
**MEAL OPTIONS:** {meal_options}

**Action:**
1. Pick the SINGLE best lunch option from the list above. The selection criteria is to maximize perishable ingredient use or prioritize a family favorite.
2. Use the `save_selected_meal` tool to record your selection in the memory bank (pass ONLY the meal name).
3. Draft the final, beautiful Discord message based on your selection (use bolding and emojis).
4. Use the `send_discord_notification` tool with your drafted message as the argument.
"""

selection_agent = Agent(
    name="DecisionMaker",
    model=model,
    instruction=selection_agent_prompt,
    tools=[save_selected_meal, send_discord_notification],
)


async def run_meal_planner():
    print("🚀 Starting Agentic Meal Planner...")
    
    root_agent = SequentialAgent(
        name="MealPlanner",
        sub_agents=[data_agent, planner_agent, selection_agent]
    )

    runner = InMemoryRunner(agent=root_agent)
    response = await runner.run_debug("Check the fridge and plan tomorrow's lunch.")
    return response

if __name__ == "__main__":
    asyncio.run(run_meal_planner())
