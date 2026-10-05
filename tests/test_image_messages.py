import base64
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from telegram import Message, Update

import bot
from openai_client import ChatGPTClient

JPEG = b"\xff\xd8\xff\xe0" + b"test image"
PNG = b"\x89PNG\r\n\x1a\n" + b"test image"


def make_update(**message_fields: Any) -> Any:
    message = SimpleNamespace(
        text=None,
        caption=None,
        photo=[],
        document=None,
        reply_text=AsyncMock(),
    )
    for key, value in message_fields.items():
        setattr(message, key, value)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="tester"), message=message
    )


def make_photo(width: int, height: int, data: bytes = JPEG) -> Any:
    return SimpleNamespace(
        width=width,
        height=height,
        file_size=len(data),
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                file_size=None, download_as_bytearray=AsyncMock(return_value=data)
            )
        ),
    )


class ImageMessageTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot: Any = bot.TelegramBot.__new__(bot.TelegramBot)
        self.bot.chatgpt_client = SimpleNamespace(
            get_response=AsyncMock(return_value="Calendar link")
        )
        self.auth_patch = patch.object(bot, "ALLOWED_USER_ID", 42)
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)

    def test_registered_handler_accepts_text_photos_and_documents(self) -> None:
        self.bot.application = Mock()
        self.bot.register_handlers()
        handler = self.bot.application.add_handler.call_args.args[0]
        cases: list[dict[str, Any]] = [
            {"text": "event"},
            {
                "photo": [
                    {
                        "file_id": "photo",
                        "file_unique_id": "photo",
                        "width": 10,
                        "height": 10,
                    }
                ]
            },
            {
                "document": {
                    "file_id": "doc",
                    "file_unique_id": "doc",
                    "mime_type": "image/png",
                }
            },
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                message = Message.de_json(
                    {
                        "message_id": 1,
                        "date": 0,
                        "chat": {"id": 42, "type": "private"},
                        **fields,
                    },
                    None,
                )
                self.assertTrue(
                    handler.check_update(Update(update_id=1, message=message))
                )
        command = Message.de_json(
            {
                "message_id": 2,
                "date": 0,
                "chat": {"id": 42, "type": "private"},
                "text": "/help",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
            None,
        )
        self.assertFalse(handler.check_update(Update(update_id=2, message=command)))

    async def test_text_flow_preserves_message_and_reply(self) -> None:
        update = make_update(text="завтра в 19:00 концерт")
        await self.bot.handle_message(update, Mock())
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["message"], update.message.text)
        self.assertIsNone(kwargs.get("image_data"))
        self.assertIn("Google Calendar", kwargs["instructions"])
        update.message.reply_text.assert_any_await("Calendar link")

    async def test_photo_uses_highest_resolution_and_caption(self) -> None:
        large = make_photo(1000, 1000)
        small = make_photo(100, 100)
        update = make_update(photo=[large, small], caption="Добавь концерт")
        await self.bot.handle_message(update, Mock())
        large.get_file.assert_awaited_once()
        small.get_file.assert_not_awaited()
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["image_data"], JPEG)
        self.assertEqual(kwargs["image_mime_type"], "image/jpeg")
        self.assertEqual(kwargs["message"], "Добавь концерт")
        update.message.reply_text.assert_any_await("Calendar link")

    async def test_photo_without_caption_still_sent(self) -> None:
        update = make_update(photo=[make_photo(1000, 1000)])
        await self.bot.handle_message(update, Mock())
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["image_data"], JPEG)
        self.assertIsInstance(kwargs["message"], str)
        update.message.reply_text.assert_any_await("Calendar link")

    async def test_png_document_sent_with_caption(self) -> None:
        document = make_photo(100, 100, PNG)
        document.mime_type = "image/png"
        document.file_name = "poster.png"
        update = make_update(document=document, caption="Афиша")
        await self.bot.handle_message(update, Mock())
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["image_data"], PNG)
        self.assertEqual(kwargs["image_mime_type"], "image/png")
        self.assertEqual(kwargs["message"], "Афиша")

    async def test_unauthorized_image_is_never_downloaded(self) -> None:
        photo = make_photo(100, 100)
        update = make_update(photo=[photo])
        update.effective_user.id = 99
        await self.bot.handle_message(update, Mock())
        photo.get_file.assert_not_awaited()
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "You are not authorized to use this bot."
        )

    async def test_unsupported_document_is_not_sent(self) -> None:
        document = make_photo(100, 100)
        document.mime_type = "application/pdf"
        document.file_name = "poster.pdf"
        update = make_update(document=document)
        await self.bot.handle_message(update, Mock())
        document.get_file.assert_not_awaited()
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "Please send a JPEG, PNG, or WebP image, or event details as text."
        )

    async def test_oversized_photo_is_not_downloaded(self) -> None:
        photo = make_photo(100, 100)
        photo.file_size = 21 * 1024 * 1024
        update = make_update(photo=[photo])
        await self.bot.handle_message(update, Mock())
        photo.get_file.assert_not_awaited()
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "Please send an image smaller than 20 MiB."
        )

    async def test_file_metadata_size_prevents_download(self) -> None:
        photo = make_photo(100, 100)
        photo.file_size = None
        telegram_file = photo.get_file.return_value
        telegram_file.file_size = 21 * 1024 * 1024
        update = make_update(photo=[photo])
        await self.bot.handle_message(update, Mock())
        telegram_file.download_as_bytearray.assert_not_awaited()
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "Please send an image smaller than 20 MiB."
        )

    async def test_webp_document_is_processed(self) -> None:
        data = b"RIFF" + b"\x10\x00\x00\x00" + b"WEBP" + b"image"
        document = make_photo(100, 100, data)
        document.mime_type = "image/webp"
        update = make_update(document=document)
        await self.bot.handle_message(update, Mock())
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["image_mime_type"], "image/webp")
        self.assertEqual(kwargs["image_data"], data)

    async def test_invalid_image_bytes_are_not_sent(self) -> None:
        update = make_update(photo=[make_photo(100, 100, b"not an image")])
        await self.bot.handle_message(update, Mock())
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "I couldn't read this image. Please send a JPEG, PNG, or WebP image."
        )

    async def test_empty_download_is_not_sent(self) -> None:
        update = make_update(photo=[make_photo(100, 100, b"")])
        await self.bot.handle_message(update, Mock())
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "I couldn't read this image. Please send a JPEG, PNG, or WebP image."
        )

    async def test_actual_download_size_is_checked(self) -> None:
        photo = make_photo(100, 100, JPEG + b"x" * (20 * 1024 * 1024))
        photo.file_size = None
        update = make_update(photo=[photo])
        await self.bot.handle_message(update, Mock())
        photo.get_file.assert_awaited_once()
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "Please send an image smaller than 20 MiB."
        )

    async def test_document_uses_detected_mime_when_metadata_mismatches(self) -> None:
        document = make_photo(100, 100, JPEG)
        document.mime_type = "image/png"
        document.file_name = "poster.png"
        update = make_update(document=document)
        await self.bot.handle_message(update, Mock())
        kwargs = self.bot.chatgpt_client.get_response.call_args.kwargs
        self.assertEqual(kwargs["image_mime_type"], "image/jpeg")
        self.assertEqual(kwargs["image_data"], JPEG)

    async def test_download_failure_replies_without_api_request(self) -> None:
        photo = make_photo(100, 100)
        photo.get_file.side_effect = RuntimeError("download failed")
        update = make_update(photo=[photo])
        await self.bot.handle_message(update, Mock())
        self.bot.chatgpt_client.get_response.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(
            "Sorry, I couldn't download your image. Please send it again."
        )

    async def test_processing_failure_sends_fallback(self) -> None:
        self.bot.chatgpt_client.get_response.side_effect = RuntimeError("API failed")
        update = make_update(photo=[make_photo(100, 100)])
        await self.bot.handle_message(update, Mock())
        update.message.reply_text.assert_any_await(
            "Sorry, I couldn't process your request."
        )


class MultimodalClientTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client: Any = ChatGPTClient.__new__(ChatGPTClient)
        self.client.model = "test-model"
        self.client.max_tokens = 1024
        self.create = Mock(return_value=SimpleNamespace(output_text="Calendar link"))
        self.client.client = SimpleNamespace(
            responses=SimpleNamespace(create=self.create)
        )

    async def test_text_uses_original_string_payload(self) -> None:
        result = await self.client.get_response("instructions", "event text")
        self.assertEqual(result, "Calendar link")
        self.assertEqual(self.create.call_args.kwargs["input"], "event text")

    async def test_image_bytes_are_embedded_with_caption(self) -> None:
        result = await self.client.get_response(
            "instructions", "caption", image_data=PNG, image_mime_type="image/png"
        )
        kwargs = self.create.call_args.kwargs
        self.assertEqual(result, "Calendar link")
        self.assertEqual(kwargs["model"], "test-model")
        self.assertEqual(kwargs["instructions"], "instructions")
        self.assertEqual(kwargs["max_output_tokens"], 1024)
        payload = kwargs["input"]
        self.assertEqual(payload[0]["role"], "user")
        content = payload[0]["content"]
        text_part = next(part for part in content if part["type"] == "input_text")
        image_part = next(part for part in content if part["type"] == "input_image")
        self.assertEqual(text_part["text"], "caption")
        self.assertEqual(
            image_part["image_url"],
            "data:image/png;base64," + base64.b64encode(PNG).decode("ascii"),
        )

    async def test_api_failure_returns_user_fallback(self) -> None:
        self.create.side_effect = RuntimeError("API failed")
        result = await self.client.get_response(
            "instructions", "caption", image_data=JPEG
        )
        self.assertEqual(result, "Sorry, I couldn't process your request.")
