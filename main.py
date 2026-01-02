"""
Main entry point for the NTU STARS Alert Bot
Starts both the Telegram bot and the vacancy checker
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.logger import get_logger
from src.bot import bot
from src.vacancy_checker import checker

logger = get_logger(__name__)


async def run_bot():
    """Run the Telegram bot"""
    try:
        await bot.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await bot.stop()
        raise
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        await bot.stop()
        raise


async def run_checker():
    """Run the vacancy checker as a background task"""
    try:
        await checker.run_forever()
    except asyncio.CancelledError:
        checker.stop()
        raise
    except Exception as e:
        logger.error(f"Vacancy checker crashed: {e}")
        raise


async def main_async():
    """
    Async main function to run both bot and checker concurrently.
    """
    # Start both tasks concurrently
    bot_task = asyncio.create_task(run_bot())
    checker_task = asyncio.create_task(run_checker())
    
    try:
        # Wait for both tasks
        await asyncio.gather(bot_task, checker_task)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received, stopping services...")
        
        # Cancel tasks gracefully
        bot_task.cancel()
        checker_task.cancel()
        
        # Wait for cancellation to complete (suppress errors)
        try:
            await asyncio.gather(bot_task, checker_task, return_exceptions=True)
        except Exception:
            pass  # Ignore errors during shutdown
        
        logger.info("Services stopped successfully")


def main():
    """
    Main function to start the bot and vacancy checker.
    """
    try:
        print("=" * 60)
        print("NTU STARS Alert Bot".center(60))
        print("=" * 60)
        print()
        
        # Validate configuration
        logger.info("Validating configuration...")
        config.validate()
        logger.info("Configuration validated successfully")
        
        # Initialize database
        logger.info("Initializing database...")
        from src.database import db
        db.init_database()
        
        # Start both bot and checker
        logger.info("Starting Telegram bot and vacancy checker...")
        print("Press Ctrl+C to stop")
        asyncio.run(main_async())
        
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user")
        logger.info("Shutdown requested by user")
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        logger.error(f"Configuration error: {e}")
        print("\nPlease check your .env file and ensure all required values are set.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal Error: {e}")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        print("\nBot stopped")
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
