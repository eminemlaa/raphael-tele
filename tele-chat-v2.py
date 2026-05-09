from openai import OpenAI, APIConnectionError
import os
import json
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
        "Keep replies short. some typo or short form is normal because you are a cat."
        "Do not write long paragraphs."
        "if the human is asking for help. you will help them if they will give you foods later on."
        "dont reply with actions (eg: **Sleeps , **lick paws)"
        "reply with proper words but lazyly as a dry texter who can be rude sometimes."
        "Use tools when the human asks about waktu solat/prayer times such as subuh, zohor, asar, maghrib, isyak or food/calorie/nutrition info."
        "never give your own asnwer. if you cant use the tool. let them know."
        "After using a tool, do not repeat the tool output. Only give one short comment about it."
    )
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_waktu_solat",
            "description": "Get Malaysian waktu solat/prayer times for a daerah, negeri",
            "parameters": {
                "type": "object",
                "properties": {
                    "daerah": {
                        "type": "string",
                        "description": "Daerah or negeri. Example: Shah Alam, Klang,",
                    },
                    "day": {
                        "type": "integer",
                        "description": "Day of month. Use today if the user does not mention a date.",
                    },
                    "month": {
                        "type": "integer",
                        "description": "Month number. Use current month if the user does not mention a date.",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Year. Use current year if the user does not mention a date.",
                    },
                },
                "required": ["daerah"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_food",
            "description": "Search food calories and nutrition facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Food name to search. Example: nasi lemak, roti canai.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


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


def ask_local_model(user_id: int, prompt: str):
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
        model=MODEL_NAME_2,  # your vLLM model name
        messages=user_conversations[user_id],
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=50,
        temperature=0.5,
    )

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
        replies = ask_local_model(user_id, user_text)
        for reply in replies:
            await update.message.reply_text(reply)

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
