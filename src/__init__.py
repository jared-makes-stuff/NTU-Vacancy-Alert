"""
NTU STARS Alert Bot Package
A Telegram bot that monitors NTU course vacancies and sends alerts
"""

__version__ = "1.0.0"

from .config import config
from .database import db
from .logger import get_logger
from .bot import bot
from .vacancy_checker import checker
from .vacancy_api import vacancy_api
from .vacancy_parser import VacancyParser

__all__ = ['config', 'db', 'get_logger', 'bot', 'checker', 'vacancy_api', 'VacancyParser']
