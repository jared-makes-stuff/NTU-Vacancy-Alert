"""
Logging Module
Provides centralized logging configuration for the application
"""

import logging
import sys
from pathlib import Path
from .config import config


class Logger:
    """
    Logger class implementing the Singleton pattern.
    Provides consistent logging across the application.
    """
    
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize logging configuration"""
        if self._initialized:
            return
        
        # Create logs directory if it doesn't exist
        log_dir = Path(config.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure root logger
        self._setup_root_logger()
        self._initialized = True
    
    def _setup_root_logger(self):
        """Setup root logger with file and console handlers"""
        # Get log level from config
        log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler (detailed)
        file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(detailed_formatter)
        
        # Console handler (simple)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(simple_formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    def get_logger(self, name):
        """
        Get or create a logger with the specified name.
        
        Args:
            name (str): Name of the logger (typically __name__)
        
        Returns:
            logging.Logger: Configured logger instance
        """
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]


# Global logger instance
logger_factory = Logger()


def get_logger(name):
    """
    Convenience function to get a logger.
    
    Args:
        name (str): Name of the logger (typically __name__)
    
    Returns:
        logging.Logger: Configured logger instance
    
    Example:
        >>> from logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    return logger_factory.get_logger(name)
