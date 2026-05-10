from openai import OpenAI, APIConnectionError
import os
import json
import random
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv


from datetime import datetime
from waktu_solat import get_waktu_solat_by_daerah
from food import search_food

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# OLLAMA_URL = os.getenv("OLLAMA_URL")
# MODEL_NAME = os.getenv("MODEL_NAME")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")
OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")
MODEL_NAME_2 = os.getenv("MODEL_NAME_2")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_NEWS_URL = os.getenv("SERPER_NEWS_URL", "https://google.serper.dev/news")
SERPER_PLACES_URL = os.getenv("SERPER_PLACES_URL", "https://google.serper.dev/places")
LOG_DIR = Path(os.getenv("TELEGRAM_LOG_DIR", "/opt/llm/conversation_logs"))
KNOWN_USERS_FILE = Path(os.getenv("TELEGRAM_KNOWN_USERS_FILE", "/opt/llm/known_users.json"))
PROMPT_CONFIG_FILE = Path(os.getenv("PROMPT_CONFIG_FILE", "/opt/llm/prompts.yaml"))
PROACTIVE_CHECK_SECONDS = int(os.getenv("PROACTIVE_CHECK_SECONDS", "3600"))
PROACTIVE_FIRST_SECONDS = int(os.getenv("PROACTIVE_FIRST_SECONDS", "60"))
PROACTIVE_CHANCE = float(os.getenv("PROACTIVE_CHANCE", "0.15"))

# client = ollama.Client(host=OLLAMA_URL)
client = OpenAI(
    base_url=OPENAI_API_URL,
    api_key=OPEN_AI_KEY
)

# Stores conversation history per Telegram user
user_conversations = {}
known_users = {}


def load_prompt_config() -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load prompts.yaml. Run: pip install PyYAML"
        ) from exc

    with open(PROMPT_CONFIG_FILE, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    required_keys = ["system_prompt", "proactive_prompt", "tools"]
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise RuntimeError(
            f"Missing required prompt config keys: {', '.join(missing_keys)}"
        )

    return config


PROMPT_CONFIG = load_prompt_config()
SYSTEM_PROMPT = {
    "role": "system",
    "content": PROMPT_CONFIG["system_prompt"],
}
PROACTIVE_PROMPT = PROMPT_CONFIG["proactive_prompt"]
TOOLS = PROMPT_CONFIG["tools"]


def user_to_record(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def load_known_users():
    global known_users

    if not KNOWN_USERS_FILE.exists():
        known_users = {}
        return

    with open(KNOWN_USERS_FILE, "r", encoding="utf-8") as file:
        known_users = json.load(file)


def save_known_users():
    KNOWN_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(KNOWN_USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(known_users, file, indent=2)


def remember_user(user):
    known_users[str(user.id)] = user_to_record(user)
    save_known_users()


def get_user_label(user) -> str:
    if isinstance(user, dict):
        username_value = user.get("username")
        first_name = user.get("first_name")
        last_name = user.get("last_name")
        user_id = user.get("id")
    else:
        username_value = user.username
        first_name = user.first_name
        last_name = user.last_name
        user_id = user.id

    username = f"@{username_value}" if username_value else "no_username"
    full_name = " ".join(
        part for part in [first_name, last_name] if part
    ) or "no_name"

    return f"{full_name} ({username}, id={user_id})"


def log_conversation(user, role: str, text: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    user_id = user.get("id") if isinstance(user, dict) else user.id
    log_file = LOG_DIR / f"user_{user_id}.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {role.upper()} {get_user_label(user)}\n")
        file.write(f"{text}\n\n")


def format_serper_news(data: dict, query: str, limit: int) -> str:
    news_items = data.get("news") or data.get("organic") or []
    if not news_items:
        return f"No fresh news found for '{query}'. tragic."

    lines = [f"Latest news for: {query}"]

    for index, item in enumerate(news_items[:limit], 1):
        title = item.get("title") or "Untitled"
        source = item.get("source") or item.get("site") or "Unknown source"
        date = item.get("date") or item.get("publishedDate") or "No date"
        snippet = item.get("snippet") or ""
        link = item.get("link") or item.get("url") or ""

        lines.append(
            "\n".join(
                part for part in [
                    f"{index}. {title}",
                    f"Source: {source} | Date: {date}",
                    f"Summary: {snippet}" if snippet else "",
                ] if part
            )
        )

    return "\n\n".join(lines)


def format_place_hours(hours) -> str:
    if isinstance(hours, dict):
        return "\n".join(f"- {day}: {time}" for day, time in hours.items())

    if isinstance(hours, list):
        return "\n".join(f"- {item}" for item in hours)

    if isinstance(hours, str):
        return hours

    return ""


def format_serper_places(data: dict, place: str, limit: int) -> str:
    places = data.get("places") or data.get("localResults") or []
    if not places:
        return f"No place info found for '{place}'. maybe google is also lazy."

    lines = [f"{place}"]

    for index, item in enumerate(places[:limit], 1):
        title = item.get("title") or item.get("name") or "Unknown place"
        address = item.get("address") or item.get("formattedAddress") or ""
        phone = item.get("phoneNumber") or item.get("phone") or ""
        rating = item.get("rating")
        rating_count = item.get("ratingCount") or item.get("reviews")
        website = item.get("website") or ""
        link = item.get("link") or item.get("url") or item.get("placeIdSearch") or ""
        hours = format_place_hours(
            item.get("openingHours")
            or item.get("hours")
            or item.get("workingHours")
        )

        rating_text = ""
        if rating:
            rating_text = f"Rating: {rating}"
            if rating_count:
                rating_text += f" ({rating_count} reviews)"

        lines.append(
            "\n".join(
                part for part in [
                    f"{index}. {title}",
                    f"Address: {address}" if address else "",
                    rating_text,
                    f"Phone: {phone}" if phone else "",
                    f"Hours:\n{hours}" if hours else "Hours: Not shown in result",
                    # f"Website: {website}" if website else "",
                    # f"Link: {link}" if link else "",
                ] if part
            )
        )

    return "\n\n".join(lines)


def search_latest_news(query: str, country: str = "my", language: str = "en", limit: int = 5) -> str:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is not set.")

    limit = max(1, min(int(limit or 5), 10))
    payload = {
        "q": query,
        "gl": country or "my",
        "hl": language or "en",
        "num": limit,
        "tbs": "qdr:d",
    }

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    response = requests.post(
        SERPER_NEWS_URL,
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()

    return format_serper_news(response.json(), query, limit)



def search_place_info(place: str, country: str = "my", language: str = "en", limit: int = 3) -> str:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is not set.")

    limit = max(1, min(int(limit or 3), 5))
    payload = {
        "q": place,
        "gl": country or "my",
        "hl": language or "en",
        "num": limit,
    }
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    response = requests.post(
        SERPER_PLACES_URL,
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()

    return format_serper_places(response.json(), place, limit)


def run_tool(name: str, arguments: dict) -> str:
    if name == "get_waktu_solat":
        today = datetime.now()
        return get_waktu_solat_by_daerah(
            daerah=arguments["daerah"],
            day=int(arguments.get("day") or today.day),
            month=int(arguments.get("month") or today.month),
            year=int(arguments.get("year") or today.year),
        )

    if name == "search_food":
        return search_food(arguments["query"])

    if name == "search_latest_news":
        return search_latest_news(
            query=arguments["query"],
            country=arguments.get("country") or "my",
            language=arguments.get("language") or "en",
            limit=arguments.get("limit") or 5,
        )

    if name == "search_place_info":
        return search_place_info(
            place=arguments["place"],
            country=arguments.get("country") or "my",
            language=arguments.get("language") or "en",
            limit=arguments.get("limit") or 3,
        )

    raise ValueError(f"unknown tool: {name}")


def message_to_dict(message):
    message_dict = {
        "role": message.role,
        "content": message.content or "",
    }

    if message.tool_calls:
        message_dict["tool_calls"] = [
            tool_call.model_dump()
            for tool_call in message.tool_calls
        ]

    return message_dict


def ask_local_model(
    user_id: int,
    prompt: str,
    tool_choice="auto",
    include_tool_comment: bool = True,
):
    if user_id not in user_conversations:
        user_conversations[user_id] = [SYSTEM_PROMPT]

    user_conversations[user_id].append({
        "role": "user",
        "content": prompt
    })

    if len(user_conversations[user_id]) > 100:
        user_conversations[user_id] = (
            [SYSTEM_PROMPT] + user_conversations[user_id][-10:]
        )

    request_args = {
        "model": MODEL_NAME_2,  # your vLLM model name
        "messages": user_conversations[user_id],
        "max_tokens": 50,
        "temperature": 0.5,
    }

    if tool_choice != "none":
        request_args["tools"] = TOOLS
        request_args["tool_choice"] = tool_choice

    response = client.chat.completions.create(**request_args)

    message = response.choices[0].message
    user_conversations[user_id].append(message_to_dict(message))

    if message.tool_calls:
        tool_results = []

        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                tool_result = run_tool(tool_call.function.name, arguments)
            except Exception as e:
                tool_result = f"tool error: {e}"

            tool_results.append(tool_result)
            user_conversations[user_id].append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

        if not include_tool_comment:
            answer = "\n\n".join(tool_results)
            user_conversations[user_id].append({
                "role": "assistant",
                "content": answer
            })
            return tool_results

        response = client.chat.completions.create(
            model=MODEL_NAME_2,
            messages=user_conversations[user_id],
            max_tokens=200,
            temperature=0.5,
        )

        answer = response.choices[0].message.content.strip()
        user_conversations[user_id].append({
            "role": "assistant",
            "content": answer
        })

        replies = ["\n\n".join(tool_results)]
        if answer:
            replies.append(answer)

        return replies

    answer = (message.content or "").strip()

    return [answer]


def reset_conversation(user_id: int):
    user_conversations[user_id] = [SYSTEM_PROMPT]


async def send_random_owner_question(context: ContextTypes.DEFAULT_TYPE):
    for user_id, user_record in list(known_users.items()):
        if random.random() > PROACTIVE_CHANCE:
            continue

        try:
            replies = ask_local_model(
                int(user_id),
                PROACTIVE_PROMPT,
                tool_choice="none",
            )

            for reply in replies:
                log_conversation(user_record, "bot", reply)
                await context.bot.send_message(chat_id=int(user_id), text=reply)
        except Exception as e:
            log_conversation(user_record, "error", f"proactive message failed: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    remember_user(update.effective_user)
    reset_conversation(user_id)

    reply = "yeah. send something."
    log_conversation(update.effective_user, "bot", reply)
    await update.message.reply_text(reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    user_text = update.message.text.strip()
    remember_user(user)
    log_conversation(user, "user", user_text)

    if user_text.lower() == "new chat":
        reset_conversation(user_id)
        reply = "new chat. happy now?"
        log_conversation(user, "bot", reply)
        await update.message.reply_text(reply)
        return

    #await update.message.reply_text("typing...")

    try:
        replies = ask_local_model(user_id, user_text)
        for reply in replies:
            log_conversation(user, "bot", reply)
            await update.message.reply_text(reply)

    except APIConnectionError:
        reply = "model not running. tragic."
        log_conversation(user, "bot", reply)
        await update.message.reply_text(reply)

    except Exception as e:
        reply = f"error: {e}"
        log_conversation(user, "bot", reply)
        await update.message.reply_text(reply)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Please set TELEGRAM_BOT_TOKEN environment variable.")

    load_known_users()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(
            send_random_owner_question,
            interval=PROACTIVE_CHECK_SECONDS,
            first=PROACTIVE_FIRST_SECONDS,
        )
    else:
        print('JobQueue not available. Install with: pip install "python-telegram-bot[job-queue]"')

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
