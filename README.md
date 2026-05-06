# Raphael Telegram Bot

A simple Telegram chatbot powered by a local Ollama model.

Raphael is a sarcastic talking cat that replies casually, keeps responses short, and can also fetch Malaysian waktu solat by daerah using a custom `waktu_solat` tool.

## Features

- Telegram bot integration
- Local LLM response using Ollama
- Per-user conversation history
- Reset chat with `new chat`
- Custom system prompt for Raphael's personality
- Waktu solat lookup by daerah
- Uses `zone-waktu-solat.json` to map daerah to JAKIM zone codes
- Calls `api.waktusolat.app` for prayer time data

## Example Messages

Normal chat:
```text
hello
```

Waktu solat lookup:
```text
waktu solat shah alam
solat klang
solat kota bharu
prayer time johor bahru
```


Reset conversation::
```text
new chat
```

## Requirements
- Python 3.10+
- Telegram Bot Token
- Ollama running locally or on a reachable server
- A model already pulled in Ollama
