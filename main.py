from time import sleep

from bot import TelegramBot
from config import STOP_POLLING_TELEGRAM


def main() -> None:
    """Start the bot."""
    bot = TelegramBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped by user")


def dummy_loop() -> None:
    print("Dummy loop")
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("Loop stopped by user")
        return


if __name__ == "__main__":
    if STOP_POLLING_TELEGRAM:
        dummy_loop()
    else:
        main()
