import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ALLOWED_USER_ID, TELEGRAM_TOKEN
from openai_client import ChatGPTClient

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress httpx logs
httpx_logger = logging.getLogger("httpx")
httpx_logger.disabled = True

class TelegramBot:
    def __init__(self):
        logger.info("Initializing TelegramBot...")
        self.chatgpt_client = ChatGPTClient()
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Register handlers
        self.register_handlers()

    def register_handlers(self):
        """Register command and message handlers."""
        logger.info("Registering command and message handlers...")
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Message handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when the command /start is issued."""
        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning("Unauthorized access attempt by user ID: %s", update.effective_user.id)
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        logger.info("Received /start command from user: %s", update.effective_user.username)
        await update.message.reply_text('Welcome to the ChatGPT Telegram Bot! Send me a message and I will respond using ChatGPT.')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a help message when the command /help is issued."""
        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning("Unauthorized access attempt by user ID: %s", update.effective_user.id)
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        logger.info("Received /help command from user: %s", update.effective_user.username)
        help_text = """
        How to use this bot:
        
        1. Simply send a message, and ChatGPT will respond.
        2. Use /start to see the welcome message.
        3. Use /help to see this help message.
        """
        await update.message.reply_text(help_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and respond with ChatGPT."""
        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning("Unauthorized access attempt by user ID: %s", update.effective_user.id)
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        user_message = update.message.text
        logger.info("Received message from user %s: %s", update.effective_user.username, user_message)

        # Inform user that the bot is processing
        await update.message.reply_text("Processing your request...")

        # Get response from ChatGPT
        try:
            logger.info("Sending message to ChatGPT: %s", user_message)
            response = await self.chatgpt_client.get_response(user_message)
            logger.info("Received response from ChatGPT: %s", response)
        except Exception as e:
            logger.error("Error while processing message: %s", e)
            response = "Sorry, I couldn't process your request."

        # Send response back to user
        await update.message.reply_text(response)

    def run(self):
        """Run the bot until the user presses Ctrl-C"""
        logger.info("Starting bot...")
        self.application.run_polling()
