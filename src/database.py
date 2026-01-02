"""
Database module for NTU STARS Alert Bot
Handles PostgreSQL database operations for user and alert management
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from .config import config
from .logger import get_logger

logger = get_logger(__name__)


class Database:
    """
    Database class implementing the Singleton pattern.
    Handles all PostgreSQL database operations for user and alert management.
    
    Attributes:
        db_config (dict): Database connection configuration
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize database configuration"""
        if self._initialized:
            return
        
        self.db_config = config.get_db_config()
        self._initialized = True
        logger.info("Database instance initialized")
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        
        Yields:
            psycopg2.connection: Database connection object
        
        Raises:
            psycopg2.Error: If database connection or operation fails
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            yield conn
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def init_database(self):
        """
        Initialize database tables and indexes.
        Creates all necessary tables if they don't exist.
        
        Returns:
            bool: True if successful
        
        Raises:
            psycopg2.Error: If table creation fails
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Users table - simplified without NTU credentials
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id BIGINT PRIMARY KEY,
                        username VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_paused BOOLEAN DEFAULT FALSE,
                        paused_until TIMESTAMP,
                        pause_reason VARCHAR(50)
                    )
                """)
                
                # Alerts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
                        course_code VARCHAR(50) NOT NULL,
                        index_number VARCHAR(50) NOT NULL,
                        academic_year VARCHAR(10) DEFAULT '2025',
                        semester VARCHAR(10) DEFAULT '2',
                        is_active BOOLEAN DEFAULT TRUE,
                        last_checked TIMESTAMP,
                        last_vacancy_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(telegram_id, course_code, index_number, academic_year, semester)
                    )
                """)
                
                # Alert history table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alert_history (
                        id SERIAL PRIMARY KEY,
                        alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
                        telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
                        course_code VARCHAR(50) NOT NULL,
                        index_number VARCHAR(50) NOT NULL,
                        vacancy_count INTEGER NOT NULL,
                        waitlist_count INTEGER NOT NULL,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        notification_sent BOOLEAN DEFAULT FALSE
                    )
                """)
                
                # Create indexes for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alerts_active 
                    ON alerts(is_active, last_checked)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_history_alert_id 
                    ON alert_history(alert_id, checked_at DESC)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_history_telegram_id 
                    ON alert_history(telegram_id, checked_at DESC)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_history_composite 
                    ON alert_history(telegram_id, alert_id, checked_at DESC)
                """)
                
                conn.commit()
                logger.info("Database tables initialized successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    # User operations
    def add_user(self, telegram_id, username):
        """
        Add or update a user in the database.
        
        Args:
            telegram_id (int): Telegram user ID
            username (str): Telegram username
        
        Returns:
            bool: True if successful
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (telegram_id, username)
                    VALUES (%s, %s)
                    ON CONFLICT (telegram_id) 
                    DO UPDATE SET 
                        username = EXCLUDED.username,
                        updated_at = CURRENT_TIMESTAMP,
                        is_active = TRUE
                """, (telegram_id, username))
                conn.commit()
                logger.info(f"User {telegram_id} ({username}) added/updated successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to add/update user {telegram_id}: {e}")
            raise
    
    def get_user(self, telegram_id):
        """
        Get user by telegram ID.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            dict: User data, or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT * FROM users WHERE telegram_id = %s AND is_active = TRUE
                """, (telegram_id,))
                user = cursor.fetchone()
                return user
        except Exception as e:
            logger.error(f"Failed to get user {telegram_id}: {e}")
            return None
    
    def deactivate_user(self, telegram_id):
        """
        Deactivate a user (soft delete).
        Also deactivates all their alerts.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            bool: True if user was deactivated
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET is_active = FALSE WHERE telegram_id = %s
                """, (telegram_id,))
                affected = cursor.rowcount
                conn.commit()
                
                if affected > 0:
                    logger.info(f"User {telegram_id} deactivated")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to deactivate user {telegram_id}: {e}")
            raise
    
    def delete_user(self, telegram_id):
        """
        Completely delete a user and all their data from the database.
        This will cascade delete all alerts and alert history.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            bool: True if user was deleted
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM users WHERE telegram_id = %s
                """, (telegram_id,))
                affected = cursor.rowcount
                conn.commit()
                
                if affected > 0:
                    logger.info(f"User {telegram_id} and all associated data deleted")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to delete user {telegram_id}: {e}")
            raise
    
    def pause_user(self, telegram_id, duration_minutes=20):
        """
        Pause alert checking for a user temporarily.
        
        Args:
            telegram_id (int): Telegram user ID
            duration_minutes (int): Duration to pause in minutes (default: 20)
        
        Returns:
            bool: True if user was paused
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET is_paused = TRUE,
                        paused_until = CURRENT_TIMESTAMP + INTERVAL '%s minutes',
                        pause_reason = 'manual',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = %s
                """, (duration_minutes, telegram_id))
                affected = cursor.rowcount
                conn.commit()
                
                if affected > 0:
                    logger.info(f"User {telegram_id} paused for {duration_minutes} minutes")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to pause user {telegram_id}: {e}")
            raise
    
    def resume_user(self, telegram_id):
        """
        Resume alert checking for a paused user.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            bool: True if user was resumed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET is_paused = FALSE,
                        paused_until = NULL,
                        pause_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = %s
                """, (telegram_id,))
                affected = cursor.rowcount
                conn.commit()
                
                if affected > 0:
                    logger.info(f"User {telegram_id} resumed")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to resume user {telegram_id}: {e}")
            raise
    
    def stop_user(self, telegram_id):
        """
        Stop all alerts for a user permanently.
        Pauses the user indefinitely and deactivates all alerts.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            bool: True if user was stopped
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Pause user indefinitely
                cursor.execute("""
                    UPDATE users 
                    SET is_paused = TRUE,
                        paused_until = NULL,
                        pause_reason = 'stopped',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = %s
                """, (telegram_id,))
                
                # Deactivate all alerts
                cursor.execute("""
                    UPDATE alerts 
                    SET is_active = FALSE
                    WHERE telegram_id = %s
                """, (telegram_id,))
                
                alerts_affected = cursor.rowcount
                conn.commit()
                
                logger.info(f"User {telegram_id} stopped ({alerts_affected} alerts deactivated)")
                return True
        except Exception as e:
            logger.error(f"Failed to stop user {telegram_id}: {e}")
            raise
    
    def check_user_pause_status(self, telegram_id):
        """
        Check if a user is paused and auto-resume if pause period expired.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            dict: Pause status with keys 'is_paused', 'paused_until', 'pause_reason'
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT is_paused, paused_until, pause_reason
                    FROM users 
                    WHERE telegram_id = %s
                """, (telegram_id,))
                
                result = cursor.fetchone()
                if not result:
                    return {'is_paused': False, 'paused_until': None, 'pause_reason': None}
                
                # Auto-resume if pause period expired
                if result['is_paused'] and result['paused_until'] and result['pause_reason'] == 'manual':
                    cursor.execute("""
                        UPDATE users
                        SET is_paused = FALSE,
                            paused_until = NULL,
                            pause_reason = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE telegram_id = %s 
                        AND paused_until < CURRENT_TIMESTAMP
                        RETURNING is_paused
                    """, (telegram_id,))
                    
                    updated = cursor.fetchone()
                    if updated:
                        conn.commit()
                        logger.info(f"User {telegram_id} auto-resumed after pause expiry")
                        result['is_paused'] = False
                        result['paused_until'] = None
                        result['pause_reason'] = None
                
                return result
        except Exception as e:
            logger.error(f"Failed to check pause status for {telegram_id}: {e}")
            return {'is_paused': False, 'paused_until': None, 'pause_reason': None}
    
    # Alert operations
    def add_alert(self, telegram_id, course_code, index_number, academic_year=None, semester=None):
        """
        Add a new alert for a user.
        If academic_year and semester are not provided, fetches current values from NTU API.
        
        Args:
            telegram_id (int): Telegram user ID
            course_code (str): Course code (e.g., 'SC2103')
            index_number (str): Index number (e.g., '10272')
            academic_year (str, optional): Academic year (fetches from API if None)
            semester (str, optional): Semester (fetches from API if None)
        
        Returns:
            int: Alert ID if created, None if already exists
        """
        # Use current semester from API (with fallback to config defaults)
        if academic_year is None:
            academic_year = config.DEFAULT_ACADEMIC_YEAR
            logger.debug(f"Using academic year: {academic_year}")
        if semester is None:
            semester = config.DEFAULT_SEMESTER
            logger.debug(f"Using semester: {semester}")
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO alerts (telegram_id, course_code, index_number, academic_year, semester)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (telegram_id, course_code.upper(), index_number, academic_year, semester))
                alert_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Alert created: ID={alert_id}, User={telegram_id}, Course={course_code}, Index={index_number}")
                return alert_id
        except psycopg2.IntegrityError:
            # Alert already exists
            logger.warning(f"Alert already exists: User={telegram_id}, Course={course_code}, Index={index_number}")
            return None
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            raise
    
    def get_user_alerts(self, telegram_id):
        """
        Get all active alerts for a user.
        
        Args:
            telegram_id (int): Telegram user ID
        
        Returns:
            list: List of alert dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT * FROM alerts 
                    WHERE telegram_id = %s AND is_active = TRUE
                    ORDER BY created_at DESC
                """, (telegram_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to get alerts for user {telegram_id}: {e}")
            return []
    
    def get_all_active_alerts(self):
        """
        Get all active alerts.
        Excludes alerts for paused users.
        
        Returns:
            list: List of alert dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT 
                        a.id, a.telegram_id, a.course_code, a.index_number,
                        a.academic_year, a.semester, a.last_vacancy_count
                    FROM alerts a
                    JOIN users u ON a.telegram_id = u.telegram_id
                    WHERE a.is_active = TRUE 
                    AND u.is_active = TRUE
                    AND (
                        u.is_paused = FALSE 
                        OR (u.is_paused = TRUE AND u.paused_until IS NOT NULL AND u.paused_until < CURRENT_TIMESTAMP)
                    )
                    ORDER BY a.last_checked ASC NULLS FIRST
                """)
                alerts = cursor.fetchall()
                return alerts
        except Exception as e:
            logger.error(f"Failed to get all active alerts: {e}")
            return []
    
    def remove_alert(self, alert_id, telegram_id):
        """
        Remove an alert (soft delete).
        
        Args:
            alert_id (int): Alert ID
            telegram_id (int): Telegram user ID (for verification)
        
        Returns:
            bool: True if alert was removed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE alerts 
                    SET is_active = FALSE 
                    WHERE id = %s AND telegram_id = %s
                """, (alert_id, telegram_id))
                affected = cursor.rowcount
                conn.commit()
                
                if affected > 0:
                    logger.info(f"Alert {alert_id} removed by user {telegram_id}")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to remove alert {alert_id}: {e}")
            raise
    
    def update_alert_check(self, alert_id, vacancy_count, waitlist_count):
        """
        Update alert check information and log history.
        
        Args:
            alert_id (int): Alert ID
            vacancy_count (int): Current vacancy count
            waitlist_count (int): Current waitlist count
        
        Returns:
            bool: True if successful
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get alert details for history
                cursor.execute("""
                    SELECT telegram_id, course_code, index_number 
                    FROM alerts 
                    WHERE id = %s
                """, (alert_id,))
                alert_info = cursor.fetchone()
                
                if not alert_info:
                    logger.warning(f"Alert {alert_id} not found for update")
                    return False
                
                telegram_id, course_code, index_number = alert_info
                
                # Update alert
                cursor.execute("""
                    UPDATE alerts 
                    SET last_checked = CURRENT_TIMESTAMP,
                        last_vacancy_count = %s
                    WHERE id = %s
                """, (vacancy_count, alert_id))
                
                # Log history with denormalized data
                cursor.execute("""
                    INSERT INTO alert_history (
                        alert_id, telegram_id, course_code, index_number,
                        vacancy_count, waitlist_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (alert_id, telegram_id, course_code, index_number, vacancy_count, waitlist_count))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update alert check for {alert_id}: {e}")
            raise
    
    def mark_notification_sent(self, alert_id):
        """
        Mark the latest history entry as notified.
        
        Args:
            alert_id (int): Alert ID
        
        Returns:
            bool: True if successful
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE alert_history 
                    SET notification_sent = TRUE
                    WHERE alert_id = %s AND id = (
                        SELECT id FROM alert_history 
                        WHERE alert_id = %s 
                        ORDER BY checked_at DESC 
                        LIMIT 1
                    )
                """, (alert_id, alert_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to mark notification sent for alert {alert_id}: {e}")
            raise
    
    def get_alert_history(self, alert_id, limit=10):
        """
        Get history for an alert.
        
        Args:
            alert_id (int): Alert ID
            limit (int): Maximum number of history entries to return
        
        Returns:
            list: List of history dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT * FROM alert_history 
                    WHERE alert_id = %s 
                    ORDER BY checked_at DESC 
                    LIMIT %s
                """, (alert_id, limit))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to get history for alert {alert_id}: {e}")
            return []


# Global database instance
db = Database()
