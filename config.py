import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram settings
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID", "0")

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Default model for ChatGPT
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Maximum token context for ChatGPT
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
