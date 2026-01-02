"""
NTU STARS Public Vacancy API Client
Handles fetching course vacancy information from the public API
"""

import requests
from datetime import datetime
from .config import config
from .logger import get_logger
from .vacancy_parser import VacancyParser

logger = get_logger(__name__)


class VacancyApiClient:
    """
    Client for interacting with the NTU STARS public vacancy API.
    Uses the non-authenticated endpoint to fetch course vacancy information.
    Implements the Singleton pattern.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(VacancyApiClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the API client"""
        if self._initialized:
            return
        
        self.base_url = "https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy2"
        self.timeout = config.REQUEST_TIMEOUT
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        self._initialized = True
        logger.info("Vacancy API client initialized")
    
    def is_service_available(self):
        """
        Check if the NTU vacancy service is available (8am - 10pm Singapore time).
        
        Returns:
            tuple: (bool, str) - (is_available, message)
        """
        # Get current Singapore time (UTC+8)
        import pytz
        sg_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(sg_tz)
        current_hour = now.hour
        
        # Service available 8am to 10pm
        if 8 <= current_hour < 22:
            return True, "Service available"
        else:
            return False, f"NTU STARS vacancy service is only available from 8:00 AM to 10:00 PM (Singapore time). Current time: {now.strftime('%I:%M %p')}"
    
    def get_course_vacancies(self, course_code):
        """
        Get vacancy information for all indexes of a course.
        
        Args:
            course_code (str): Course code (e.g., 'SC2103')
        
        Returns:
            dict: Dictionary with 'success', 'data' or 'error', 'error_message'
                  On success: {'success': True, 'data': [list of indexes]}
                  On error: {'success': False, 'error': error_type, 'error_message': message}
        
        Example success return:
            {
                'success': True,
                'data': [
                    {
                        'index': '10294',
                        'vacancy': 0,
                        'waitlist': 0,
                        'classes': [...]
                    },
                    ...
                ]
            }
        
        Example error return:
            {
                'success': False,
                'error': 'service_unavailable',
                'error_message': 'Service only available 8am-10pm',
                'status_code': 503
            }
        """
        try:
            # Check if service is available
            is_available, message = self.is_service_available()
            if not is_available:
                logger.warning(f"Service not available: {message}")
                return {
                    'success': False,
                    'error': 'time_restriction',
                    'error_message': message
                }
            
            logger.debug(f"Fetching vacancies for course: {course_code}")
            
            # Make POST request
            data = {"subj": course_code.upper()}
            response = requests.post(
                self.base_url,
                headers=self.headers,
                data=data,
                timeout=self.timeout
            )
            
            # Check for HTTP errors
            if response.status_code != 200:
                error_msg = f"Server Error (Status {response.status_code})"
                if response.status_code == 503:
                    error_msg += " - Service Unavailable (Server may be down or under maintenance)"
                elif response.status_code == 500:
                    error_msg += " - Internal Server Error"
                elif response.status_code == 403:
                    error_msg += " - Access Forbidden"
                elif response.status_code == 404:
                    error_msg += " - Endpoint Not Found"
                
                logger.error(f"HTTP error {response.status_code} for {course_code}")
                return {
                    'success': False,
                    'error': 'http_error',
                    'error_message': error_msg,
                    'status_code': response.status_code
                }
            
            # Parse HTML response
            indexes = VacancyParser.parse_vacancy_html(response.text, course_code)
            
            if indexes is None:
                # Parsing error occurred
                return {
                    'success': False,
                    'error': 'parse_error',
                    'error_message': 'Failed to parse response from server'
                }
            
            logger.info(f"Found {len(indexes)} indexes for course {course_code}")
            return {
                'success': True,
                'data': indexes
            }
            
        except requests.Timeout:
            error_msg = "Request Timeout - Server took too long to respond"
            logger.error(f"Timeout fetching vacancies for {course_code}")
            return {
                'success': False,
                'error': 'timeout',
                'error_message': error_msg
            }
        except requests.ConnectionError:
            error_msg = "Connection Error - Unable to reach NTU server. Check your internet connection."
            logger.error(f"Connection error fetching vacancies for {course_code}")
            return {
                'success': False,
                'error': 'connection_error',
                'error_message': error_msg
            }
        except requests.RequestException as e:
            error_msg = f"Network Error - {str(e)}"
            logger.error(f"Request error fetching vacancies for {course_code}: {e}")
            return {
                'success': False,
                'error': 'request_error',
                'error_message': error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected Error - {str(e)}"
            logger.error(f"Unexpected error fetching vacancies for {course_code}: {e}")
            return {
                'success': False,
                'error': 'unknown_error',
                'error_message': error_msg
            }
    
    def get_index_vacancy(self, course_code, index_number):
        """
        Get vacancy information for a specific course index.
        
        Args:
            course_code (str): Course code (e.g., 'SC2103')
            index_number (str): Index number (e.g., '10294')
        
        Returns:
            dict: Dictionary with 'success', 'data' or 'error', 'error_message'
                  On success: {'success': True, 'data': {index info dict}}
                  On error: {'success': False, 'error': error_type, 'error_message': message}
        """
        try:
            result = self.get_course_vacancies(course_code)
            
            if not result['success']:
                return result
            
            all_indexes = result['data']
            
            for index_info in all_indexes:
                if index_info['index'] == str(index_number):
                    logger.debug(f"Found vacancy for {course_code}/{index_number}: {index_info['vacancy']}")
                    return {
                        'success': True,
                        'data': index_info
                    }
            
            logger.warning(f"Index {index_number} not found for course {course_code}")
            return {
                'success': False,
                'error': 'index_not_found',
                'error_message': f"Index {index_number} not found for course {course_code}"
            }
            
        except Exception as e:
            logger.error(f"Error getting vacancy for {course_code}/{index_number}: {e}")
            return {
                'success': False,
                'error': 'unknown_error',
                'error_message': f"Error: {str(e)}"
            }
    
    def format_index_display(self, index_info):
        """
        Format index information for display to users.
        Delegates to VacancyParser.
        
        Args:
            index_info (dict): Index information dictionary
        
        Returns:
            str: Formatted string for display
        """
        return VacancyParser.format_index_display(index_info)
    
    def format_course_display(self, course_code, indexes):
        """
        Format all indexes of a course for display.
        Delegates to VacancyParser.
        
        Args:
            course_code (str): Course code
            indexes (list): List of index dictionaries
        
        Returns:
            str: Formatted string for display
        """
        return VacancyParser.format_course_display(course_code, indexes)


# Global client instance
vacancy_api = VacancyApiClient()
