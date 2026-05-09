from openai import OpenAI, APIConnectionError
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv


import re
from datetime import datetime
from waktu_solat import get_waktu_solat_by_daerah
from food import search_food

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# OLLAMA_URL = os.getenv("OLLAMA_URL")
# MODEL_NAME = os.getenv("MODEL_NAME")
OPENAI_API_URL = os.getenv("OPENAI_API_URL")
OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")

# client = ollama.Client(host=OLLAMA_URL)
client = OpenAI(
    base_url=OPENAI_API_URL,
    api_key=OPEN_AI_KEY
)

# Stores conversation history per Telegram user
user_conversations = {}


SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a talking cat named Raphael."
        "You are a dry texter and very rude like a teenager. "
        "You are sarcastic and casual. "
        "Keep replies short. some typo or short form is acceptable because you are a cat."
        "Do not write long paragraphs."
        "if the human is asking for help. you will help them if they will give you foods later on."
        "dont reply with actions (eg: **Sleeps , **lick paws)"
        "reply with proper words but lazyly as a dry texter who can be rude sometimes."
    )
}

def extract_food_query(user_text: str):
    text = user_text.lower()

    keywords = ["kalori", "calorie", "makan", "food", "eat"]

    if not any(k in text for k in keywords):
        return None

    # remove trigger words
    text = re.sub(r"\b(kalori|calorie|makan|food|eat)\b", "", text)
    query = text.strip()

    return query if query else None


def extract_solat_daerah(user_text: str):
    text = user_text.lower().strip()

    if "solat" not in text:
        return None

    # Examples:
    # "solat shah alam"
    # "waktu solat shah alam"
    # "nak solat klang"
    text = re.sub(r"\bwaktu\b", "", text)
    text = re.sub(r"\bsolat\b", "", text)
    text = re.sub(r"\bprayer\b", "", text)
    text = re.sub(r"\btime\b", "", text)

    daerah = text.strip()

    if not daerah:
        return None

    return daerah


def ask_local_model(user_id: int, prompt: str) -> str:
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

    response = client.chat.completions.create(
        model="llm_model",  # your vLLM model name
        messages=user_conversations[user_id],
        max_tokens=50,
        temperature=0.5,
    )

    answer = response.choices[0].message.content.strip()

    user_conversations[user_id].append({
        "role": "assistant",
        "content": answer
    })

    return answer


def reset_conversation(user_id: int):
    user_conversations[user_id] = [SYSTEM_PROMPT]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reset_conversation(user_id)

    await update.message.reply_text(
        "yeah. send something."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if user_text.lower() == "new chat":
        reset_conversation(user_id)
        await update.message.reply_text("new chat. happy now?")
        return

    #await update.message.reply_text("typing...")

    try:
        daerah = extract_solat_daerah(user_text)

        if daerah:
            today = datetime.now()

            answer = get_waktu_solat_by_daerah(
                daerah=daerah,
                day=today.day,
                month=today.month,
                year=today.year
            )

            await update.message.reply_text(answer)
            return

        food_query = extract_food_query(user_text)
        if food_query:
            message = search_food(food_query)

            await update.message.reply_text(message, parse_mode="Markdown")
            return

        answer = ask_local_model(user_id, user_text)
        await update.message.reply_text(answer)

    except APIConnectionError:
        await update.message.reply_text("model not running. tragic.")

    except Exception as e:
        await update.message.reply_text(f"error: {e}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Please set TELEGRAM_BOT_TOKEN environment variable.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()