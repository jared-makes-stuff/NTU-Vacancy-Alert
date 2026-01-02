"""
NTU STARS Alert Telegram Bot
Main bot implementation with user registration and alert management
"""

import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)
from .config import config
from .database import db
from .logger import get_logger
from .vacancy_api import vacancy_api

logger = get_logger(__name__)

# Conversation states
(ADD_ALERT_COURSE, ADD_ALERT_INDEX, DISPLAY_VACANCIES_COURSE) = range(3)


class TelegramBot:
    """
    Telegram Bot implementing the Singleton pattern.
    Handles all bot interactions and user management.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(TelegramBot, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the bot"""
        if self._initialized:
            return
        
        self.application = None
        self._initialized = True
        logger.info("Telegram bot instance created")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /start command.
        
        Args:
            update: Telegram update object
            context: Callback context
        """
        user = update.effective_user
        logger.info(f"User {user.id} ({user.username}) started bot")
        
        # Auto-register user
        db.add_user(update.effective_user.id, update.effective_user.username)
        
        welcome_message = (
            f"Welcome to NTU STARS Alert Bot, {user.first_name}!\n\n"
            "I'll help you monitor course vacancies and notify you when slots open up.\n\n"
            "Available Commands:\n"
            "/add - Add a course alert\n"
            "/displayVacancies - View vacancies for any course\n"
            "/list - View your active alerts\n"
            "/remove <ID> - Remove an alert\n"
            "/stop - Stop and delete all alerts\n"
            "/help - Show this help message\n"
            "/cancel - Cancel current operation\n\n"
            "To get started, use /add to create your first alert!\n"
            "Or use /displayVacancies to check vacancies without creating an alert\n\n"
            "Note: NTU vacancy service is only available 8am-10pm Singapore time."
        )
        
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "*NTU STARS Alert Bot Help*\n\n"
            "*Commands:*\n"
            "/start - Start the bot\n"
            "/add - Add a new course vacancy alert\n"
            "/displayVacancies - View vacancies for any course\n"
            "/list - View all your active alerts\n"
            "/remove <ID> - Remove an alert by ID\n"
            "/stop - Stop and delete all alerts\n"
            "/help - Show this help message\n"
            "/cancel - Cancel current operation\n\n"
            "*How it works:*\n"
            "1. Use /add to add alerts for courses you want to monitor\n"
            "2. Select the course and index you want to track\n"
            "3. Get notified instantly when vacancies open up!\n\n"
            "*Quick Check:*\n"
            "- Use /displayVacancies to check vacancies without creating an alert\n"
            "- Browse through indexes with navigation buttons\n\n"
            "*Data Management:*\n"
            "- Use /stop to delete all your alerts and data\n"
            "- You can restart anytime with /start\n\n"
            "*Important:*\n"
            "NTU vacancy service is only available 8am-10pm Singapore time\n"
            "No login required - uses public NTU data"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def display_vacancies_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start display vacancies conversation"""
        # Auto-register user if not exists
        db.add_user(update.effective_user.id, update.effective_user.username)
        
        await update.message.reply_text(
            "*Display Course Vacancies*\n\n"
            "Please enter the *course code* to view vacancies (e.g., SC2103, CE2002, CC0006):\n\n"
            "Use /cancel to abort.",
            parse_mode='Markdown'
        )
        return DISPLAY_VACANCIES_COURSE
    
    async def display_vacancies_course(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive course code and display vacancies with pagination"""
        course_code = update.message.text.strip().upper()
        context.user_data['display_course'] = course_code
        
        await update.message.reply_text(f"Fetching vacancies for {course_code}...")
        
        # Fetch all indexes for this course
        result = vacancy_api.get_course_vacancies(course_code)
        
        if not result['success']:
            # Show error with details
            error_msg = result['error_message']
            if result.get('status_code'):
                error_msg += f"\n\nTechnical details: Status Code {result['status_code']}"
            
            await update.message.reply_text(
                f"{error_msg}\n\n"
                "Please try again later or check if the course code is correct.\n\n"
                "Use /displayVacancies to try again or /cancel to abort."
            )
            return DISPLAY_VACANCIES_COURSE
        
        indexes = result['data']
        
        if not indexes:
            await update.message.reply_text(
                f"No indexes found for course {course_code}.\n"
                "Please check the course code and try again.\n\n"
                "Use /displayVacancies to try again or /cancel to abort."
            )
            return DISPLAY_VACANCIES_COURSE
        
        # Store indexes in user_data for pagination
        context.user_data['display_indexes'] = indexes
        context.user_data['display_page'] = 0
        
        # Send first page with pagination
        await self._send_display_page(update, context, is_new_message=True)
        
        return ConversationHandler.END
    
    async def _send_display_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_new_message=False):
        """Send a page of vacancies for display mode"""
        course_code = context.user_data.get('display_course')
        all_indexes = context.user_data.get('display_indexes', [])
        current_page = context.user_data.get('display_page', 0)
        
        INDEXES_PER_PAGE = 5  # Show 5 indexes per page
        total_pages = (len(all_indexes) + INDEXES_PER_PAGE - 1) // INDEXES_PER_PAGE
        
        # Calculate start and end index for current page
        start_idx = current_page * INDEXES_PER_PAGE
        end_idx = min(start_idx + INDEXES_PER_PAGE, len(all_indexes))
        page_indexes = all_indexes[start_idx:end_idx]
        
        # Build message
        message = f"*Course: {course_code}* - Vacancy Display\n\n"
        message += f"Showing indexes (Page {current_page + 1}/{total_pages}):\n\n"
        
        for idx_info in page_indexes:
            vacancy_indicator = "[AVAILABLE]" if idx_info['vacancy'] > 0 else "[FULL]"
            message += f"{vacancy_indicator} *Index {idx_info['index']}*\n"
            message += f"   Vacancies: {idx_info['vacancy']} | Waitlist: {idx_info['waitlist']}\n"
            
            # Show class schedule (limit to first 3 classes)
            classes_to_show = idx_info['classes'][:3]
            for cls in classes_to_show:
                message += f"   • {cls['type']} - {cls['day']} {cls['time']}\n"
            
            if len(idx_info['classes']) > 3:
                message += f"   • ... and {len(idx_info['classes']) - 3} more classes\n"
            
            message += "\n"
        
        message += f"\nTotal: {len(all_indexes)} indexes"
        
        # Create pagination buttons
        keyboard = []
        nav_buttons = []
        
        # Previous button
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("< Previous", callback_data=f"display_{current_page - 1}"))
        
        # Page indicator
        nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="display_info"))
        
        # Next button
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next >", callback_data=f"display_{current_page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send or edit message
        try:
            if is_new_message:
                await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                # This is a callback query, edit the existing message
                await update.callback_query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                await update.callback_query.answer()
        except Exception as e:
            logger.error(f"Error sending display page: {e}")
            # Fallback
            if is_new_message:
                await update.message.reply_text(
                    f"*Course: {course_code}*\n\n"
                    f"Found {len(all_indexes)} indexes.\n\n"
                    "Use /displayVacancies to try again.",
                    parse_mode='Markdown'
                )
    
    async def handle_display_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle display vacancies pagination button clicks"""
        query = update.callback_query
        
        if query.data == "display_info":
            # Just acknowledge, don't change page
            await query.answer("Current page")
            return
        
        # Extract page number from callback data
        if query.data.startswith("display_"):
            page_num = int(query.data.split("_")[1])
            context.user_data['display_page'] = page_num
            
            # Update the message with new page
            await self._send_display_page(update, context, is_new_message=False)
    
    async def add_alert_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start add alert conversation"""
        # Auto-register user if not exists
        db.add_user(update.effective_user.id, update.effective_user.username)
        
        await update.message.reply_text(
            "*Add Course Alert*\n\n"
            "Please enter the *course code* (e.g., SC2103, CE2002):\n\n"
            "Use /cancel to abort.",
            parse_mode='Markdown'
        )
        return ADD_ALERT_COURSE
    
    async def add_alert_course(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive course code and show available indexes"""
        course_code = update.message.text.strip().upper()
        context.user_data['alert_course'] = course_code
        
        await update.message.reply_text(f"Fetching indexes for {course_code}...")
        
        # Fetch all indexes for this course
        result = vacancy_api.get_course_vacancies(course_code)
        
        if not result['success']:
            # Show error with details
            error_msg = result['error_message']
            if result.get('status_code'):
                error_msg += f"\n\nTechnical details: Status Code {result['status_code']}"
            
            await update.message.reply_text(
                f"{error_msg}\n\n"
                "Please try again later or check if the course code is correct.\n\n"
                "Use /add to try again or /cancel to abort."
            )
            return ADD_ALERT_COURSE
        
        indexes = result['data']
        
        if not indexes:
            await update.message.reply_text(
                f"No indexes found for course {course_code}.\n"
                "Please check the course code and try again.\n\n"
                "Use /add to try again or /cancel to abort."
            )
            return ADD_ALERT_COURSE
        
        # Store indexes in user_data for pagination
        context.user_data['all_indexes'] = indexes
        context.user_data['current_page'] = 0
        
        # Send first page with pagination
        await self._send_index_page(update, context, is_new_message=True)
        
        return ADD_ALERT_INDEX
    
    async def _send_index_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_new_message=False):
        """Send a page of indexes with pagination controls"""
        course_code = context.user_data.get('alert_course')
        all_indexes = context.user_data.get('all_indexes', [])
        current_page = context.user_data.get('current_page', 0)
        
        INDEXES_PER_PAGE = 5  # Show 5 indexes per page
        total_pages = (len(all_indexes) + INDEXES_PER_PAGE - 1) // INDEXES_PER_PAGE
        
        # Calculate start and end index for current page
        start_idx = current_page * INDEXES_PER_PAGE
        end_idx = min(start_idx + INDEXES_PER_PAGE, len(all_indexes))
        page_indexes = all_indexes[start_idx:end_idx]
        
        # Build message
        message = f"*Course: {course_code}*\n\n"
        message += f"Available indexes (Page {current_page + 1}/{total_pages}):\n\n"
        
        for idx_info in page_indexes:
            vacancy_indicator = "[AVAILABLE]" if idx_info['vacancy'] > 0 else "[FULL]"
            message += f"{vacancy_indicator} *Index {idx_info['index']}*\n"
            message += f"   Vacancies: {idx_info['vacancy']} | Waitlist: {idx_info['waitlist']}\n"
            
            # Show class schedule (limit to first 3 classes)
            classes_to_show = idx_info['classes'][:3]
            for cls in classes_to_show:
                message += f"   • {cls['type']} - {cls['day']} {cls['time']}\n"
            
            if len(idx_info['classes']) > 3:
                message += f"   • ... and {len(idx_info['classes']) - 3} more classes\n"
            
            message += "\n"
        
        message += "\nEnter the *index number* to monitor, or use buttons to navigate:"
        
        # Create pagination buttons
        keyboard = []
        nav_buttons = []
        
        # Previous button
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("< Previous", callback_data=f"page_{current_page - 1}"))
        
        # Page indicator
        nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="page_info"))
        
        # Next button
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next >", callback_data=f"page_{current_page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send or edit message
        try:
            if is_new_message:
                await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                # This is a callback query, edit the existing message
                await update.callback_query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                await update.callback_query.answer()
        except Exception as e:
            logger.error(f"Error sending index page: {e}")
            # Fallback
            if is_new_message:
                await update.message.reply_text(
                    f"*Course: {course_code}*\n\n"
                    f"Found {len(all_indexes)} indexes.\n\n"
                    "Please enter the *index number* you want to monitor:",
                    parse_mode='Markdown'
                )
    
    async def handle_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination button clicks"""
        query = update.callback_query
        
        if query.data == "page_info":
            # Just acknowledge, don't change page
            await query.answer("Current page")
            return
        
        # Extract page number from callback data
        if query.data.startswith("page_"):
            page_num = int(query.data.split("_")[1])
            context.user_data['current_page'] = page_num
            
            # Update the message with new page
            await self._send_index_page(update, context, is_new_message=False)
    
    async def add_alert_index(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive index number and create alert"""
        index_number = update.message.text.strip()
        course_code = context.user_data.get('alert_course')
        
        await update.message.reply_text("Creating alert and checking current vacancy...")
        
        try:
            # Auto-resume user if they're adding a new alert
            pause_status = db.check_user_pause_status(update.effective_user.id)
            if pause_status['pause_reason'] == 'stopped':
                db.resume_user(update.effective_user.id)
                logger.info(f"User {update.effective_user.id} auto-resumed from stopped state")
            
            alert_id = db.add_alert(
                telegram_id=update.effective_user.id,
                course_code=course_code,
                index_number=index_number
            )
            
            if alert_id:
                # Immediately check current vacancy using public API
                result = vacancy_api.get_index_vacancy(course_code, index_number)
                
                if result['success']:
                    vacancy_info = result['data']
                    
                    # Update the alert with current vacancy
                    db.update_alert_check(
                        alert_id,
                        vacancy_info['vacancy'],
                        vacancy_info['waitlist']
                    )
                    logger.info(f"Initial vacancy check for alert {alert_id}: {vacancy_info['vacancy']} vacancies")
                    
                    # Show current status with class schedule
                    status_msg = (
                        f"*Alert Created!*\n\n"
                        f"Course: {course_code}\n"
                        f"Index: {index_number}\n"
                        f"Alert ID: {alert_id}\n\n"
                        f"*Current Status:*\n"
                        f"   Vacancies: {vacancy_info['vacancy']}\n"
                        f"   Waitlist: {vacancy_info['waitlist']}\n\n"
                        f"*Class Schedule:*\n"
                    )
                    
                    for cls in vacancy_info['classes']:
                        status_msg += f"   • {cls['type']} - {cls['day']} {cls['time']} @ {cls['venue']}\n"
                    
                    status_msg += "\n"
                    
                    if vacancy_info['vacancy'] > 0:
                        status_msg += "*Slots are available now!* Register quickly!\n\n"
                    else:
                        status_msg += "I'll notify you when a vacancy opens up!\n\n"
                    
                    status_msg += f"Checking every {config.CHECK_INTERVAL // 60} minutes."
                    
                    await update.message.reply_text(status_msg, parse_mode='Markdown')
                else:
                    # Show error from API
                    error_msg = result['error_message']
                    if result.get('status_code'):
                        error_msg += f"\nStatus Code: {result['status_code']}"
                    
                    await update.message.reply_text(
                        f"*Alert Created!*\n\n"
                        f"Course: {course_code}\n"
                        f"Index: {index_number}\n"
                        f"Alert ID: {alert_id}\n\n"
                        f"Warning: Could not verify current vacancy:\n{error_msg}\n\n"
                        f"I'll notify you when a vacancy opens up!\n"
                        f"Checking every {config.CHECK_INTERVAL // 60} minutes.",
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    "This alert already exists!\n"
                    "Use /list to view your active alerts."
                )
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            await update.message.reply_text(
                f"Failed to create alert: {str(e)}\n"
                "Please try again later."
            )
        
        return ConversationHandler.END
    
    async def list_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all user alerts"""
        # Auto-register user if not exists
        db.add_user(update.effective_user.id, update.effective_user.username)
        
        # Check pause status
        pause_status = db.check_user_pause_status(update.effective_user.id)
        
        alerts = db.get_user_alerts(update.effective_user.id)
        
        if not alerts:
            message = "You have no active alerts.\n"
            message += "Use /add to create your first alert!"
        else:
            message = "*Your Active Alerts:*\n\n"
            
            for alert in alerts:
                message += (
                    f"*ID:* {alert['id']}\n"
                    f"*Course:* {alert['course_code']}\n"
                    f"*Index:* {alert['index_number']}\n"
                    f"*Last Vacancy:* {alert['last_vacancy_count']}\n"
                )
                
                if alert['last_checked']:
                    message += f"*Last Checked:* {alert['last_checked'].strftime('%Y-%m-%d %H:%M')}\n"
                
                message += "\n"
            
            message += f"\nUse /remove <ID> to remove an alert."
        
        # Add pause status
        if pause_status['is_paused']:
            if pause_status['pause_reason'] == 'stopped':
                message += "\n\n*Status:* Permanently stopped"
                message += "\nUse /add to reactivate"
            elif pause_status['paused_until']:
                message += f"\n\n*Status:* Paused until {pause_status['paused_until'].strftime('%H:%M')}"
                message += "\nUse /resume to end pause early"
            else:
                message += "\n\n*Status:* Paused"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def remove_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove an alert"""
        if not context.args:
            await update.message.reply_text(
                "Please provide an alert ID.\n"
                "Usage: /remove <ID>\n"
                "Use /list to see your alert IDs."
            )
            return
        
        try:
            alert_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid alert ID. Please provide a number.")
            return
        
        if db.remove_alert(alert_id, update.effective_user.id):
            await update.message.reply_text(
                f"Alert {alert_id} has been removed."
            )
        else:
            await update.message.reply_text(
                "Alert not found or you don't have permission to remove it."
            )
    
    async def stop_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop all alerts permanently"""
        # Check if user exists
        user = db.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text(
                "You have no active alerts to stop."
            )
            return
        
        # Get count of active alerts
        alerts = db.get_user_alerts(update.effective_user.id)
        alert_count = len(alerts)
        
        if db.stop_user(update.effective_user.id):
            await update.message.reply_text(
                "*All Alerts Stopped*\n\n"
                f"Deactivated {alert_count} alert(s).\n\n"
                "Your account is paused indefinitely.\n"
                "The bot will NOT check vacancies.\n\n"
                "To start monitoring again:\n"
                "  1. Use /add to create new alerts\n"
                "  2. Your account will be automatically reactivated",
                parse_mode='Markdown'
            )
            logger.info(f"User {update.effective_user.id} stopped all alerts ({alert_count} alerts)")
        else:
            await update.message.reply_text(
                "Failed to stop alerts. Please try again."
            )
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current conversation"""
        await update.message.reply_text(
            "Operation cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    def setup(self):
        """
        Set up the bot application and handlers.
        """
        try:
            # Create application with optimized timeout settings for cleaner shutdown
            from telegram.request import HTTPXRequest
            
            request = HTTPXRequest(
                connection_pool_size=8,
                pool_timeout=1.0,  # Faster timeout for shutdown
                read_timeout=10.0,
                write_timeout=10.0,
                connect_timeout=5.0
            )
            
            self.application = (
                Application.builder()
                .token(config.TELEGRAM_BOT_TOKEN)
                .request(request)
                .build()
            )
            
            # Register command handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("list", self.list_alerts))
            self.application.add_handler(CommandHandler("remove", self.remove_alert))
            self.application.add_handler(CommandHandler("stop", self.stop_alerts))
            
            # Register display vacancies conversation handler
            display_vacancies_conv = ConversationHandler(
                entry_points=[CommandHandler("displayvacancies", self.display_vacancies_start)],
                states={
                    DISPLAY_VACANCIES_COURSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.display_vacancies_course)],
                },
                fallbacks=[CommandHandler("cancel", self.cancel)]
            )
            
            self.application.add_handler(display_vacancies_conv)
            
            # Register callback handler for display vacancies pagination (outside conversation)
            self.application.add_handler(CallbackQueryHandler(self.handle_display_pagination, pattern="^display_"))
            
            # Register add alert conversation handler
            add_alert_conv = ConversationHandler(
                entry_points=[CommandHandler("add", self.add_alert_start)],
                states={
                    ADD_ALERT_COURSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_alert_course)],
                    ADD_ALERT_INDEX: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.add_alert_index),
                        CallbackQueryHandler(self.handle_pagination, pattern="^page_")
                    ],
                },
                fallbacks=[CommandHandler("cancel", self.cancel)]
            )
            
            self.application.add_handler(add_alert_conv)
            
            logger.info("Bot handlers registered")
            
        except Exception as e:
            logger.error(f"Failed to setup bot: {e}")
            raise
    
    async def start(self):
        """
        Start the bot asynchronously.
        """
        try:
            if not self.application:
                self.setup()
            
            logger.info("Bot started successfully")
            print("NTU STARS Alert Bot is running...")
            
            # Initialize and start the application
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """
        Stop the bot gracefully with improved error handling.
        """
        try:
            if self.application and self.application.updater:
                logger.info("Stopping bot...")
                
                # Stop polling first
                if self.application.updater.running:
                    await self.application.updater.stop()
                
                # Stop application
                if self.application.running:
                    await self.application.stop()
                
                # Shutdown (cleanup resources)
                await self.application.shutdown()
                
                logger.info("Bot stopped gracefully")
        except asyncio.CancelledError:
            # This is expected during shutdown
            logger.info("Bot shutdown cancelled - this is normal during shutdown")
        except Exception as e:
            # Log but don't raise - we want shutdown to complete
            logger.warning(f"Non-critical error during shutdown: {e}")
            logger.info("Bot stopped (with minor warnings)")
    
    def run(self):
        """
        Start the bot synchronously (blocking).
        This method blocks until the bot is stopped.
        """
        try:
            # Validate configuration
            config.validate()
            
            # Initialize database
            db.init_database()
            
            # Setup and run bot
            self.setup()
            
            print("NTU STARS Alert Bot is running...")
            print("Press Ctrl+C to stop")
            
            # Run bot
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise


# Global bot instance
bot = TelegramBot()
