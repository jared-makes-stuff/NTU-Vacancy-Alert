"""
Setup Script for Database Initialization
Run this once to create all database tables
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.database import db
from src.logger import get_logger

logger = get_logger(__name__)


def main():
    """Initialize the database"""
    try:
        print("=" * 60)
        print("NTU STARS Alert Bot - Database Setup".center(60))
        print("=" * 60)
        print()
        
        # Validate configuration
        print("Validating configuration...")
        config.validate()
        
        # Initialize database
        print("Connecting to database...")
        print(f"  Host: {config.DB_HOST}")
        print(f"  Database: {config.DB_NAME}")
        print(f"  User: {config.DB_USER}")
        print()
        
        print("Creating tables...")
        db.init_database()
        
        print()
        print("=" * 60)
        print("Database setup completed successfully!".center(60))
        print("=" * 60)
        print()
        print("You can now run the bot with: python main.py")
        
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
        print("\nPlease check your .env file.")
        sys.exit(1)
    except Exception as e:
        print(f"\nSetup Error: {e}")
        logger.error(f"Setup error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
