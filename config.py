import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Default model for ChatGPT
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Maximum token context for ChatGPT
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
