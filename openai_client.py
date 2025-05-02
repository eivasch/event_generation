import openai

from config import MAX_TOKENS, OPENAI_API_KEY, OPENAI_MODEL

# Configure OpenAI API client
openai.api_key = OPENAI_API_KEY


class ChatGPTClient:
    def __init__(self) -> None:
        self.model = OPENAI_MODEL
        self.max_tokens = MAX_TOKENS

        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    async def get_response(self, instructions: str, message: str) -> str | None:
        """
        Send a message to ChatGPT and get a response.

        Args:
            message (str): The message to send to ChatGPT.

        Returns:
            str: The response from ChatGPT.
        """
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=message,
                max_output_tokens=self.max_tokens,
            )
            return response.output_text
        except Exception as e:
            print(f"Error getting response from ChatGPT: {e}")
            return "Sorry, I couldn't process your request."
