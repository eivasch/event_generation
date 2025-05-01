# Telegram Event Generation

Telegram Event Generation is a Python-based Telegram bot that integrates with OpenAI's ChatGPT to provide conversational AI capabilities. Users can send messages to the bot, and it will respond using ChatGPT.

## Features

- Telegram bot integration using `python-telegram-bot`.
- ChatGPT integration via OpenAI API.
- Asynchronous message handling for efficient communication.

## Requirements

- Python 3.13 or higher
- Telegram Bot Token
- OpenAI API Key

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/telegram-event-generation.git
   cd telegram-event-generation
   ```

2. Install Poetry if not already installed:
   ```bash
   pip install poetry
   ```

3. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

4. Create a `.env` file in the project root and add the following environment variables:
   ```env
   TELEGRAM_TOKEN=your-telegram-bot-token
   OPENAI_API_KEY=your-openai-api-key
   OPENAI_MODEL=gpt-4o  # Optional, default is gpt-4o
   MAX_TOKENS=1024      # Optional, default is 1024
   ```

## Usage

1. Run the bot:
   ```bash
   poetry run python main.py
   ```

2. Interact with the bot on Telegram by sending messages. The bot will respond using ChatGPT.

## Project Structure

- `main.py`: Entry point for starting the bot.
- `bot.py`: Contains the Telegram bot implementation and message handlers.
- `openai_client.py`: Handles communication with OpenAI's ChatGPT API.
- `config.py`: Loads and manages environment variables.
- `pyproject.toml`: Project configuration and dependencies.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.
