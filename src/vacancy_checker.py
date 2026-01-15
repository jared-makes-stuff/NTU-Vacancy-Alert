"""
Vacancy Checker Module
Background task that monitors course vacancies and sends notifications
"""

import asyncio
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from .config import config
from .database import db
from .logger import get_logger
from .vacancy_api import vacancy_api

logger = get_logger(__name__)

DATA_SOURCE_URL = "https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy"
DATA_SOURCE_LINK = f"[{DATA_SOURCE_URL}]({DATA_SOURCE_URL})"


class VacancyChecker:
    """
    Vacancy Checker implementing the Singleton pattern.
    Runs as a background task to monitor course vacancies.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(VacancyChecker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the vacancy checker"""
        if self._initialized:
            return
        
        self.bot = None
        self.running = False
        self._initialized = True
        logger.info("Vacancy checker instance created")
    
    async def check_alert(self, alert):
        """
        Check a single alert for vacancy changes.
        
        Args:
            alert (dict): Alert information from database
        
        Returns:
            bool: True if check was successful
        """
        try:
            # Get vacancy info using public API
            result = vacancy_api.get_index_vacancy(
                alert['course_code'],
                alert['index_number']
            )
            
            if not result['success']:
                # Log the error but don't fail completely
                logger.warning(
                    f"Could not get vacancy for alert {alert['id']} "
                    f"({alert['course_code']}/{alert['index_number']}): {result.get('error_message', 'Unknown error')}"
                )
                return False
            
            vacancy_info = result['data']
            
            # Update database
            db.update_alert_check(
                alert['id'],
                vacancy_info['vacancy'],
                vacancy_info['waitlist']
            )
            
            # Check if we should send notification
            old_vacancy = alert.get('last_vacancy_count', 0)
            new_vacancy = vacancy_info['vacancy']
            
            # Send notification if vacancy opened up (was 0, now > 0)
            if old_vacancy == 0 and new_vacancy > 0:
                await self.send_notification(alert, vacancy_info)
                db.mark_notification_sent(alert['id'])
            
            logger.info(
                f"Checked alert {alert['id']}: "
                f"{alert['course_code']}/{alert['index_number']} - "
                f"Vacancy: {new_vacancy}, Waitlist: {vacancy_info['waitlist']}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking alert {alert['id']}: {e}")
            return False
    
    async def send_notification(self, alert, vacancy_info):
        """
        Send vacancy notification to user.
        
        Args:
            alert (dict): Alert information
            vacancy_info (dict): Current vacancy information
        """
        try:
            message = (
                "*VACANCY ALERT!*\n\n"
                f"*Course:* {alert['course_code']}\n"
                f"*Index:* {alert['index_number']}\n"
                f"*Vacancies:* {vacancy_info['vacancy']}\n"
                f"*Waitlist:* {vacancy_info['waitlist']}\n\n"
                "Hurry! Slots may fill up quickly!\n\n"
                f"Data source: {DATA_SOURCE_LINK}"
            )
            
            # Create button for registration link
            keyboard = [
                [InlineKeyboardButton("Register Now", url="https://wish.wis.ntu.edu.sg/pls/webexe/ldap_login.login?w_url=https://wish.wis.ntu.edu.sg/pls/webexe/aus_stars_planner.main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.send_message(
                chat_id=alert['telegram_id'],
                text=message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            logger.info(f"Notification sent to user {alert['telegram_id']} for alert {alert['id']}")
            
        except Exception as e:
            logger.error(f"Failed to send notification for alert {alert['id']}: {e}")
    
    async def check_all_alerts(self):
        """Check all active alerts"""
        try:
            alerts = db.get_all_active_alerts()
            
            if not alerts:
                logger.debug("No active alerts to check")
                return
            
            logger.info(f"Checking {len(alerts)} active alerts...")
            
            # Group alerts by (course_code, index_number) to avoid duplicate API calls
            grouped_alerts = {}
            for alert in alerts:
                key = (alert['course_code'], alert['index_number'])
                if key not in grouped_alerts:
                    grouped_alerts[key] = []
                grouped_alerts[key].append(alert)
            
            logger.info(f"Grouped into {len(grouped_alerts)} unique course/index combinations")
            
            # Check each unique course/index combination once
            for (course_code, index_number), alert_list in grouped_alerts.items():
                if not self.running:
                    break
                
                # Get vacancy info once for this course/index
                result = vacancy_api.get_index_vacancy(course_code, index_number)
                
                if not result['success']:
                    logger.warning(
                        f"Could not get vacancy for {course_code}/{index_number}: "
                        f"{result.get('error_message', 'Unknown error')}"
                    )
                    # Small delay before next check
                    await asyncio.sleep(2)
                    continue
                
                vacancy_info = result['data']
                
                # Update all alerts for this course/index
                for alert in alert_list:
                    try:
                        # Update database
                        db.update_alert_check(
                            alert['id'],
                            vacancy_info['vacancy'],
                            vacancy_info['waitlist']
                        )
                        
                        # Check if we should send notification
                        old_vacancy = alert.get('last_vacancy_count', 0)
                        new_vacancy = vacancy_info['vacancy']
                        
                        # Send notification if vacancy opened up (was 0, now > 0)
                        if old_vacancy == 0 and new_vacancy > 0:
                            await self.send_notification(alert, vacancy_info)
                            db.mark_notification_sent(alert['id'])
                        
                        logger.debug(
                            f"Updated alert {alert['id']}: "
                            f"{course_code}/{index_number} - "
                            f"Vacancy: {new_vacancy}, Waitlist: {vacancy_info['waitlist']}"
                        )
                    except Exception as e:
                        logger.error(f"Error updating alert {alert['id']}: {e}")
                
                logger.info(
                    f"Checked {course_code}/{index_number}: "
                    f"Vacancy: {vacancy_info['vacancy']}, Waitlist: {vacancy_info['waitlist']} "
                    f"({len(alert_list)} alerts updated)"
                )
                
                # Small delay between checks to avoid rate limiting
                await asyncio.sleep(2)
            
            logger.info("Completed alert check cycle")
            
        except Exception as e:
            logger.error(f"Error in check_all_alerts: {e}")
    
    async def run_forever(self):
        """
        Run the checker loop indefinitely.
        Checks all alerts at regular intervals defined in config.
        """
        self.running = True
        self.bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        
        logger.info(f"Starting vacancy checker (interval: {config.CHECK_INTERVAL}s)")
        
        while self.running:
            try:
                await self.check_all_alerts()
                
                # Wait for next check interval
                if self.running:
                    logger.debug(f"Sleeping for {config.CHECK_INTERVAL}s")
                    await asyncio.sleep(config.CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in checker loop: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)
    
    def stop(self):
        """Stop the vacancy checker"""
        self.running = False
        logger.info("Vacancy checker stopped")


# Global checker instance
checker = VacancyChecker()
