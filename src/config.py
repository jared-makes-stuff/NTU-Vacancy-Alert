"""
Configuration Module
Loads and validates environment variables for the NTU STARS Alert Bot
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


def get_logger_for_config():
    """Get logger without circular import"""
    import logging
    return logging.getLogger(__name__)


class Config:
    """
    Configuration class implementing the Singleton pattern.
    Loads and stores all configuration from environment variables.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        if self._initialized:
            return
        
        # Database Configuration
        self.DB_HOST = os.getenv('DB_HOST', 'localhost')
        self.DB_PORT = os.getenv('DB_PORT', '5432')
        self.DB_NAME = os.getenv('DB_NAME', 'ntu_stars_alert')
        self.DB_USER = os.getenv('DB_USER', 'postgres')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD', '')
        
        # Telegram Bot Configuration
        self.TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
        
        # NTU STARS Configuration
        self.STARS_BASE_URL = os.getenv('STARS_BASE_URL', 'https://wish.wis.ntu.edu.sg/pls/webexe')
        
        # Default semester values (fallback if API fails)
        self._default_academic_year = os.getenv('DEFAULT_ACADEMIC_YEAR', '2025')
        self._default_semester = os.getenv('DEFAULT_SEMESTER', '2')
        
        # Cached dynamic values
        self._dynamic_year = None
        self._dynamic_semester = None
        self._last_fetch_time = 0
        self._cache_duration = 3600  # Cache for 1 hour
        
        # Alert Checker Configuration
        self.CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes default
        self.MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
        self.REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
        
        # Encryption Configuration
        self.ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '').encode()
        
        # Logging Configuration
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')
        
        self._initialized = True
    
    def _fetch_current_semester(self):
        """
        Fetch current semester from NTU API.
        Updates cached values if successful.
        
        Returns:
            tuple: (year, semester) or None if fetch fails
        """
        import time
        import requests
        
        logger = get_logger_for_config()
        
        # Check cache
        current_time = time.time()
        if (self._dynamic_year and self._dynamic_semester and 
            current_time - self._last_fetch_time < self._cache_duration):
            logger.debug("Using cached semester data")
            return (self._dynamic_year, self._dynamic_semester)
        
        try:
            url = f"{self.NTU_API_URL}/semesters"
            logger.info(f"Fetching current semester from {url}")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # API returns a list directly, not an object
            data = response.json()
            
            if data and len(data) > 0 and isinstance(data, list):
                latest = data[0]
                self._dynamic_year = latest['year']
                self._dynamic_semester = latest['semester']
                self._last_fetch_time = current_time
                
                logger.info(f"Fetched semester from API: {self._dynamic_year}_{self._dynamic_semester}")
                return (self._dynamic_year, self._dynamic_semester)
            else:
                logger.warning("No semesters in API response")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch semester from API: {e}")
            return None
    
    @property
    def DEFAULT_ACADEMIC_YEAR(self):
        """
        Get the current academic year.
        Fetches from API if available, falls back to env variable.
        
        Returns:
            str: Academic year (e.g., '2025')
        """
        semester_data = self._fetch_current_semester()
        if semester_data:
            return semester_data[0]
        
        logger = get_logger_for_config()
        logger.warning(f"Using fallback academic year: {self._default_academic_year}")
        return self._default_academic_year
    
    @property
    def DEFAULT_SEMESTER(self):
        """
        Get the current semester.
        Fetches from API if available, falls back to env variable.
        
        Returns:
            str: Semester number (e.g., '2')
        """
        semester_data = self._fetch_current_semester()
        if semester_data:
            return semester_data[1]
        
        logger = get_logger_for_config()
        logger.warning(f"Using fallback semester: {self._default_semester}")
        return self._default_semester
    
    def refresh_semester(self):
        """
        Force refresh of semester data from API.
        Useful to call before bulk operations.
        
        Returns:
            bool: True if refresh successful
        """
        self._last_fetch_time = 0  # Clear cache
        semester_data = self._fetch_current_semester()
        return semester_data is not None
    
    def validate(self):
        """
        Validate that all required configuration values are set.
        
        Raises:
            ValueError: If any required configuration is missing
        """
        errors = []
        
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        
        if not self.DB_PASSWORD:
            errors.append("DB_PASSWORD is required")
        
        # ENCRYPTION_KEY should be base64-encoded 32 bytes (44 characters when encoded)
        # But it's already converted to bytes in __init__, so check the bytes length
        if not self.ENCRYPTION_KEY or len(self.ENCRYPTION_KEY) != 44:
            errors.append("ENCRYPTION_KEY must be a valid base64-encoded 32-byte key (44 characters)")
        
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
        
        return True
    
    def get_db_config(self):
        """
        Get database configuration as a dictionary.
        
        Returns:
            dict: Database configuration parameters
        """
        return {
            'host': self.DB_HOST,
            'port': self.DB_PORT,
            'database': self.DB_NAME,
            'user': self.DB_USER,
            'password': self.DB_PASSWORD
        }
    
    def __repr__(self):
        """String representation (hides sensitive data)"""
        return (
            f"Config(DB_HOST={self.DB_HOST}, "
            f"DB_NAME={self.DB_NAME}, "
            f"CHECK_INTERVAL={self.CHECK_INTERVAL}s)"
        )


# Global config instance
config = Config()
