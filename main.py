from bot import TelegramBot


def main():
    """Start the bot."""
    bot = TelegramBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot stopped by user")

if __name__ == "__main__":
    main()
