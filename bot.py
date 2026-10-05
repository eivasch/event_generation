import logging
from datetime import datetime

from telegram import Document, PhotoSize, Update
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def image_mime_type(data: bytes) -> str | None:
    """Recognize supported image formats without trusting Telegram metadata."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# Suppress httpx logs
httpx_logger = logging.getLogger("httpx")
httpx_logger.disabled = True


class TelegramBot:
    def __init__(self) -> None:
        logger.info("Initializing TelegramBot...")
        self.chatgpt_client = ChatGPTClient()
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Register handlers
        self.register_handlers()

    def register_handlers(self) -> None:
        """Register command and message handlers."""
        logger.info("Registering command and message handlers...")
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Message handler
        self.application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.ALL)
                & ~filters.COMMAND,
                self.handle_message,
            )
        )

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send a welcome message when the command /start is issued."""
        if update.effective_user is None:
            logger.warning("Received message from unknown user")
            return

        if update.message is None:
            logger.warning(
                "Received None message from user: %s", update.effective_user.username
            )
            return

        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning(
                "Unauthorized access attempt by user ID: %s", update.effective_user.id
            )
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        logger.info(
            "Received /start command from user: %s", update.effective_user.username
        )
        await update.message.reply_text(
            "Welcome to the ChatGPT Telegram Bot! Send event details as text, a photo, or a JPEG/PNG/WebP image file and I will create a Google Calendar link."
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send a help message when the command /help is issued."""
        if update.effective_user is None:
            logger.warning("Received message from unknown user")
            return

        if update.message is None:
            logger.warning(
                "Received None message from user: %s", update.effective_user.username
            )
            return

        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning(
                "Unauthorized access attempt by user ID: %s", update.effective_user.id
            )
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        logger.info(
            "Received /help command from user: %s", update.effective_user.username
        )
        help_text = """
        How to use this bot:

        1. Send event details as text, a photo, or a JPEG/PNG/WebP image file (up to 20 MiB).
        Add a caption to clarify the date, time, or other details.
        2. Use /start to see the welcome message.
        3. Use /help to see this help message.
        """
        await update.message.reply_text(help_text)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages and respond with ChatGPT."""
        if update.effective_user is None:
            logger.warning("Received message from unknown user")
            return

        if update.message is None:
            logger.warning(
                "Received None message from user: %s", update.effective_user.username
            )
            return

        if update.effective_user.id != ALLOWED_USER_ID:
            logger.warning(
                "Unauthorized access attempt by user ID: %s", update.effective_user.id
            )
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        user_message = update.message.text or update.message.caption or ""
        image_data = None
        detected_mime_type = "image/jpeg"
        attachment: PhotoSize | Document | None = None
        if update.message.photo:
            attachment = max(
                update.message.photo, key=lambda photo: photo.width * photo.height
            )
        elif update.message.document:
            attachment = update.message.document
            if update.message.document.mime_type not in SUPPORTED_IMAGE_TYPES:
                await update.message.reply_text(
                    "Please send a JPEG, PNG, or WebP image, or event details as text."
                )
                return

        if attachment is None and not user_message:
            return
        if attachment is not None:
            if attachment.file_size and attachment.file_size > MAX_IMAGE_BYTES:
                await update.message.reply_text(
                    "Please send an image smaller than 20 MiB."
                )
                return
            try:
                telegram_file = await attachment.get_file()
                if (
                    telegram_file.file_size
                    and telegram_file.file_size > MAX_IMAGE_BYTES
                ):
                    await update.message.reply_text(
                        "Please send an image smaller than 20 MiB."
                    )
                    return
                image_data = bytes(await telegram_file.download_as_bytearray())
            except Exception:
                logger.error("Could not download event image")
                await update.message.reply_text(
                    "Sorry, I couldn't download your image. Please send it again."
                )
                return
            if len(image_data) > MAX_IMAGE_BYTES:
                await update.message.reply_text(
                    "Please send an image smaller than 20 MiB."
                )
                return
            actual_mime_type = image_mime_type(image_data)
            if actual_mime_type is None:
                await update.message.reply_text(
                    "I couldn't read this image. Please send a JPEG, PNG, or WebP image."
                )
                return
            detected_mime_type = actual_mime_type

        await update.message.reply_text("Processing your request...")

        # Get response from ChatGPT
        try:
            response = await self.chatgpt_client.get_response(
                message=user_message,
                instructions="Ты создаешь ссылки Google Calendar из русских сообщений.\n\n"
                "Извлекай информацию о событии из текста и изображения, если оно приложено. "
                "Учитывай подпись к изображению. Не выдумывай неразборчивые детали; "
                "если нельзя определить событие, дату или время, попроси уточнить.\n\n"
                "Если есть событие или напоминание, ответь коротко и дай одну plain text ссылку Google Calendar. "
                "Если события нет, не создавай ссылку.\n\n"
                "Правила:\n"
                "- Ссылка: https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=...&ctz=Europe/Moscow.\n"
                "- Не используй Markdown/HTML-гиперссылки.\n"
                "- Таймзона по умолчанию: Europe/Moscow.\n"
                "- Если указан старт без конца/длительности, длительность 1 час.\n"
                '- "через N часов/минут" означает старт через N часов/минут от текущего времени и является событием.\n'
                '- "напомни купить билеты через два часа" или "через два часа напомни купить билеты" = событие с названием "Купить билеты".\n'
                "- Понимай пн, вт, ср, чт, пт, сб, вс как ближайшие дни недели.\n"
                '- Время с пробелом вроде "20 00" или "9 30" понимай как 20:00 и 09:30.\n\n'
                "Сейчас " + datetime.now().strftime("%d.%m.%Y %H:%M"),
                image_data=image_data,
                image_mime_type=detected_mime_type,
            )
            logger.info("Received response from ChatGPT: %s", response)
        except Exception:
            logger.error("Error while processing message")
            response = "Sorry, I couldn't process your request."

        if response is None:
            logger.error("Received None response from ChatGPT")
            response = "Sorry, I couldn't process your request."

        # Send response back to user
        await update.message.reply_text(response)

    def run(self) -> None:
        """Run the bot until the user presses Ctrl-C"""
        logger.info("Starting bot...")
        self.application.run_polling()
