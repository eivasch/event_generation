import asyncio
import base64
import logging

import openai
from openai.types.responses import ResponseInputParam

from config import MAX_TOKENS, OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)


class ChatGPTClient:
    def __init__(self) -> None:
        self.model = OPENAI_MODEL
        self.max_tokens = MAX_TOKENS
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    async def get_response(
        self,
        instructions: str,
        message: str,
        image_data: bytes | None = None,
        image_mime_type: str = "image/jpeg",
    ) -> str | None:
        """Create a calendar response from text and an optional event image."""
        request_input: str | ResponseInputParam = message
        if image_data is not None:
            if image_mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("Unsupported image MIME type")
            encoded_image = base64.b64encode(image_data).decode("ascii")
            request_input = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": message
                            or "Read the event information in this image.",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{image_mime_type};base64,{encoded_image}",
                            "detail": "high",
                        },
                    ],
                }
            ]
        try:
            response = await asyncio.to_thread(
                self.client.responses.create,
                model=self.model,
                instructions=instructions,
                input=request_input,
                max_output_tokens=self.max_tokens,
            )
            return response.output_text
        except Exception:
            # API exceptions may include request data; do not log image payloads.
            logger.error("OpenAI request failed")
            return "Sorry, I couldn't process your request."
