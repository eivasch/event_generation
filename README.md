# Telegram Event Generation

Telegram Event Generation is a Python-based Telegram bot that integrates with OpenAI's ChatGPT to provide conversational AI capabilities. Users can send event details as text or images, and the bot responds with a Google Calendar link.

## Features

- Telegram bot integration using `python-telegram-bot`.
- Event extraction from Telegram photos and JPEG, PNG, or WebP image documents.
- Optional image captions for extra event details.
- ChatGPT integration via the OpenAI Responses API; the configured model must support image input.
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
   ALLOWED_USER_ID=your-telegram-user-id
   OPENAI_API_KEY=your-openai-api-key
   OPENAI_MODEL=gpt-5.4-mini  # Optional, default is gpt-5.4-mini
   MAX_TOKENS=1024      # Optional, default is 1024
   ```

## Usage

1. Run the bot:
   ```bash
   poetry run python main.py
   ```

2. Send event details as text, a photo, or an image file (JPEG, PNG, or WebP, up to 20 MiB). Add a caption to clarify details such as the date, time, or location. The bot reads the image and caption together and responds with a Google Calendar link. If essential details are unreadable, it asks for clarification.

Images are downloaded in memory and sent to OpenAI for analysis. Each image is processed separately, including images sent in an album. Only `ALLOWED_USER_ID` can use the bot.

## Model Evaluation

Run a live comparison of prompt variants for Russian message-to-calendar-link quality:

```bash
poetry run python scripts/evaluate_models.py
```

Optional settings:

```bash
poetry run python scripts/evaluate_models.py \
  --models gpt-5.4-mini \
  --prompts tests/fixtures/prompts_ru.json \
  --prompt-ids baseline,combined_best_guess \
  --runs 3 \
  --cases tests/fixtures/calendar_ru.json \
  --output-dir eval_reports
```

The workflow writes raw JSONL results and a Markdown summary with overall, low-cost, and quality winners by model/prompt pair. It requires `OPENAI_API_KEY` and does not change the production `OPENAI_MODEL` or bot prompt. Private evaluation sets can be stored under ignored `eval_cases/` and passed with `--cases`.

## Project Structure

- `main.py`: Entry point for starting the bot.
- `bot.py`: Contains the Telegram bot implementation and message handlers.
- `openai_client.py`: Handles communication with OpenAI's ChatGPT API.
- `config.py`: Loads and manages environment variables.
- `scripts/evaluate_models.py`: Compares model quality, latency, and estimated cost.
- `tests/fixtures/calendar_ru.json`: Russian calendar-link evaluation fixtures.
- `tests/fixtures/prompts_ru.json`: Russian prompt variants for live evaluation.
- `pyproject.toml`: Project configuration and dependencies.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.
