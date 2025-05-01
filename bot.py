from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import TELEGRAM_TOKEN
from openai_client import ChatGPTClient


class TelegramBot:
    def __init__(self):
        self.chatgpt_client = ChatGPTClient()
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Register handlers
        self.register_handlers()

    def register_handlers(self):
        """Register command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Message handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when the command /start is issued."""
        await update.message.reply_text('Welcome to the ChatGPT Telegram Bot! Send me a message and I will respond using ChatGPT.')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a help message when the command /help is issued."""
        help_text = """
        How to use this bot:
        
        1. Simply send a message, and ChatGPT will respond.
        2. Use /start to see the welcome message.
        3. Use /help to see this help message.
        """
        await update.message.reply_text(help_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and respond with ChatGPT."""
        # Get user message
        user_message = update.message.text

        # Inform user that the bot is processing
        await update.message.reply_text("Processing your request...")

        # Get response from ChatGPT
        response = await self.chatgpt_client.get_response(user_message)

        # Send response back to user
        await update.message.reply_text(response)

    def run(self):
        """Run the bot until the user presses Ctrl-C"""
        print("Starting bot...")
        self.application.run_polling()
