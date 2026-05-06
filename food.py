import requests
import os
from dotenv import load_dotenv
load_dotenv()

BASE_URL = os.getenv("URL_FOODIE")
API_KEY =  os.getenv("API_KEY_FOODIE")

def format_food_results(response_json: dict) -> str:
    if not response_json.get("success"):
        return "❌ Failed to fetch food data."

    foods = response_json.get("data", [])
    count = response_json.get("count", 0)

    if not foods:
        return "No results found."

    message_lines = [f"🍽️ *Food Results* ({count} found):\n"]

    for i, food in enumerate(foods, 1):
        line = (
            f"*{i}. {food['name']}*\n"
            f"🔥 Calories: {food['calories']} kcal\n"
            f"🍗 Protein: {food['protein']}g | 🍚 Carbs: {food['carbs']}g | 🧈 Fat: {food['fat']}g\n"
            f"📦 Serving: {food['serving']}\n"
            f"🏷️ Category: {food['category']}\n"
        )
        message_lines.append(line)

    return "\n".join(message_lines)

def search_food(query: str):

    url = f"{BASE_URL}/foods/search"
    headers = {
        "X-API-Key": API_KEY
    }
    params = {
        "q": query
    }

    response = requests.get(url, headers=headers, params=params)
    # Raise error if request failed
    response.raise_for_status()
    result =  response.json()
    final = format_food_results(result)
    return final


if __name__ == "__main__":
    result = search_food("roti canai")
    print(result)