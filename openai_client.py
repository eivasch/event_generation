import openai

from config import MAX_TOKENS, OPENAI_API_KEY, OPENAI_MODEL

# Configure OpenAI API client
openai.api_key = OPENAI_API_KEY

class ChatGPTClient:
    def __init__(self):
        self.model = OPENAI_MODEL
        self.max_tokens = MAX_TOKENS

    async def get_response(self, message):
        """
        Send a message to ChatGPT and get a response.
        
        Args:
            message (str): The message to send to ChatGPT.
            
        Returns:
            str: The response from ChatGPT.
        """
        try:
            response = openai.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": message}],
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error getting response from ChatGPT: {e}")
            return "Sorry, I couldn't process your request."
