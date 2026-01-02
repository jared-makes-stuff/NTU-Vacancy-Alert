"""
NTU STARS Vacancy HTML Parser
Handles parsing of HTML responses from the NTU STARS vacancy API
"""

from bs4 import BeautifulSoup
from .logger import get_logger

logger = get_logger(__name__)


class VacancyParser:
    """Parser for NTU STARS vacancy HTML responses"""
    
    @staticmethod
    def parse_vacancy_html(html, course_code):
        """
        Parse HTML response to extract vacancy information.
        
        Args:
            html (str): HTML response from API
            course_code (str): Course code being parsed
        
        Returns:
            list: List of index dictionaries, or None if parsing fails
            
        Example return:
            [
                {
                    'index': '10294',
                    'vacancy': 0,
                    'waitlist': 5,
                    'classes': [
                        {
                            'type': 'LEC',
                            'group': 'LE1',
                            'day': 'MON',
                            'time': '0830-1030',
                            'venue': 'LT1A'
                        },
                        ...
                    ]
                },
                ...
            ]
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the vacancy table
            table = soup.find('table', {'border': True})
            if not table:
                logger.warning(f"No vacancy table found for course {course_code}")
                return []
            
            indexes = []
            current_index = None
            
            # Skip header row
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 8:
                    continue
                
                # Get cell values
                index_num = cells[0].get_text(strip=True)
                vacancy_text = cells[1].get_text(strip=True)
                waitlist_text = cells[2].get_text(strip=True)
                class_type = cells[3].get_text(strip=True)
                group = cells[4].get_text(strip=True)
                day = cells[5].get_text(strip=True)
                time = cells[6].get_text(strip=True)
                venue = cells[7].get_text(strip=True)
                
                # Check if this is a new index or continuation
                if index_num and index_num not in ['', '&nbsp;']:
                    # New index
                    vacancy = VacancyParser._parse_number(vacancy_text)
                    waitlist = VacancyParser._parse_number(waitlist_text)
                    
                    current_index = {
                        'index': index_num,
                        'vacancy': vacancy,
                        'waitlist': waitlist,
                        'classes': []
                    }
                    indexes.append(current_index)
                
                # Add class session to current index
                if current_index and class_type:
                    current_index['classes'].append({
                        'type': class_type,
                        'group': group,
                        'day': day,
                        'time': time,
                        'venue': venue
                    })
            
            return indexes
            
        except Exception as e:
            logger.error(f"Error parsing HTML for {course_code}: {e}")
            return None
    
    @staticmethod
    def _parse_number(text):
        """
        Parse a text value to an integer, defaulting to 0 if invalid.
        
        Args:
            text (str): Text to parse
        
        Returns:
            int: Parsed number or 0
        """
        try:
            # Handle empty strings, whitespace, and HTML entities
            text = text.strip()
            if not text or text in ['', '&nbsp;', '-', 'N/A']:
                return 0
            return int(text)
        except (ValueError, AttributeError):
            return 0
    
    @staticmethod
    def format_index_display(index_info):
        """
        Format index information for display to users.
        
        Args:
            index_info (dict): Index information dictionary
        
        Returns:
            str: Formatted string for display
        """
        try:
            lines = [
                f"*Index {index_info['index']}*",
                f"   Vacancies: {index_info['vacancy']} | Waitlist: {index_info['waitlist']}",
                f"   Classes:"
            ]
            
            for cls in index_info['classes']:
                lines.append(
                    f"   • {cls['type']} ({cls['group']}) - "
                    f"{cls['day']} {cls['time']} @ {cls['venue']}"
                )
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error formatting index display: {e}")
            return f"Index {index_info.get('index', 'Unknown')}"
    
    @staticmethod
    def format_course_display(course_code, indexes):
        """
        Format all indexes of a course for display.
        
        Args:
            course_code (str): Course code
            indexes (list): List of index dictionaries
        
        Returns:
            str: Formatted string for display
        """
        if not indexes:
            return f"No indexes found for course {course_code}"
        
        lines = [f"*Course: {course_code}*", ""]
        
        for index_info in indexes:
            lines.append(VacancyParser.format_index_display(index_info))
            lines.append("")  # Empty line between indexes
        
        return '\n'.join(lines)


# Convenience instance
parser = VacancyParser()
