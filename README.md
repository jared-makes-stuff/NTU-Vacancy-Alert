# NTU STARS Alert Bot

A Telegram bot that monitors NTU course vacancies and sends instant notifications when slots open up. The bot uses the public NTU STARS vacancy API - no login credentials required.

## Features

- **Real-time vacancy notifications** - Get instant alerts when slots open
- **Track multiple courses** - Monitor as many course indexes as you need
- **Optimized checking** - Smart grouping reduces API calls by checking unique course/index combinations once
- **Pagination support** - Browse courses with many indexes easily
- **Browse mode** - View vacancies without creating alerts using `/displayvacancies`
- **Service hours** - Respects NTU STARS hours (8am-10pm Singapore time)
- **PostgreSQL backend** - Reliable data storage with complete history tracking
- **User isolation** - Each user manages only their own alerts

## How It Works

### Architecture Overview

```
+------------------+
|  Telegram User   |
+--------+---------+
         | Commands (/add, /list, /remove, /displayvacancies)
         v
+---------------------------------------------+
|           Telegram Bot (bot.py)             |
|  - Command handlers                         |
|  - Conversation states                      |
|  - Pagination for large course lists        |
+--------+------------------+-----------------+
         |                  |
         | Store alerts     | Query vacancies
         v                  v
+------------------+   +---------------------+
|  Database        |   |  Vacancy API        |
|  (database.py)   |   |  (vacancy_api.py)   |
|                  |   |                     |
|  Tables:         |   |  - get_course_      |
|  - users         |   |    vacancies()      |
|  - alerts        |   |  - get_index_       |
|  - alert_history |   |    vacancies()      |
+------------------+   +----------+----------+
         ^                        |
         |                        | POST request
         |                        v
         |               +---------------------+
         |               |  NTU STARS Public   |
         |               |  Vacancy API        |
         |               |  (aus_vacancy.      |
         |               |   check_vacancy2)   |
         |               +----------+----------+
         |                          |
         |                          | HTML response
         |                          v
         |               +---------------------+
         |               |  Vacancy Parser     |
         |               |  (vacancy_parser.py)|
         |               |  - BeautifulSoup    |
         |               |  - Parses HTML      |
         |               +----------+----------+
         |                          |
         |                          | Structured data
         +--------------------------+
                   ^
                   | Background checks every X minutes
                   |
         +---------------------+
         |  Vacancy Checker    |
         |  (vacancy_checker.py|
         |  - Groups alerts    |
         |  - Checks unique    |
         |    course/indexes   |
         |  - Sends notifications
         +---------------------+
```

### Data Flow

#### 1. User Creates an Alert
```
User: /add
Bot: Please enter the course code (e.g., CZ2006)
User: CZ2006
Bot: [Shows paginated list of available indexes]
User: [Selects index 10225]
Bot: Alert created! You'll be notified when vacancies open.

Database: INSERT INTO alerts (telegram_id, course_code, index_number, ...)
```

#### 2. Background Vacancy Checking (Optimized)
```python
# Every CHECK_INTERVAL seconds (default: 300s = 5 min)
1. Fetch all active alerts from database
2. Group alerts by (course_code, index_number)
   Example: 
   - 50 alerts for CZ2006/10225
   - 30 alerts for CE0001/12345
   = Only 2 unique combinations

3. For each unique combination:
   a. Call NTU API once: POST to aus_vacancy.check_vacancy2
   b. Parse HTML response using BeautifulSoup
   c. Extract vacancy count and waitlist count
   d. Update ALL alerts for that course/index
   e. Check if notification should be sent:
      - If old_vacancy = 0 AND new_vacancy > 0
      - Send Telegram message with button
   
Result: 2 API calls instead of 80!
```

#### 3. Notification Sent
```
When vacancy opens (0 -> 1+):

Telegram Message:
------------------
VACANCY ALERT!

Course: CZ2006
Index: 10225
Vacancies: 3
Waitlist: 0

Hurry! Slots may fill up quickly!

[Register Now] <- Clickable button
------------------

Database: 
- UPDATE alerts SET last_vacancy_count = 3
- INSERT INTO alert_history (telegram_id, course_code, index_number, vacancy_count, ...)
- UPDATE alert_history SET notification_sent = TRUE
```

#### 4. Data Source: NTU STARS Public API

The bot retrieves vacancy data from NTU's public STARS vacancy check page:
**Source:** https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy

```http
POST https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy2
Content-Type: application/x-www-form-urlencoded

acadsem=2026;1&r_course_yr=&r_subj_code=CZ2006&r_search_type=F&boption=Search

Response: HTML table with vacancy information
```

**Parser extracts:**
```html
<table>
  <tr>
    <td>10225</td>  <!-- Index -->
    <td>123</td>    <!-- Vacancy -->
    <td>0</td>      <!-- Waitlist -->
    <td>MH3</td>    <!-- Class type -->
    <td>MON 09:30-11:30</td> <!-- Schedule -->
  </tr>
</table>
```

**Becomes:**
```python
{
    'index': '10225',
    'vacancy': 123,
    'waitlist': 0,
    'class_schedule': [
        {'type': 'LEC/STUDIO', 'group': 'MH3', 'day': 'MON', 'time': '09:30-11:30', 'venue': 'LT2A', 'remark': ''}
    ]
}
```

### Database Schema

#### users table
Stores Telegram user information
```sql
telegram_id (BIGINT) - Primary key, Telegram user ID
username (VARCHAR) - Telegram username
first_name (VARCHAR) - User's first name
created_at (TIMESTAMP) - When user started using bot
is_active (BOOLEAN) - Whether user is active
```

#### alerts table
Stores user vacancy alerts
```sql
id (SERIAL) - Primary key
telegram_id (BIGINT) - Foreign key to users
course_code (VARCHAR) - Course code (e.g., CZ2006)
index_number (VARCHAR) - Index number (e.g., 10225)
last_vacancy_count (INTEGER) - Last known vacancy count
last_checked (TIMESTAMP) - Last check time
is_active (BOOLEAN) - Whether alert is active
created_at (TIMESTAMP) - When alert was created
```

**Why alert_id alone isn't efficient:**
- Query "show me MY history" would require JOIN with users
- Added denormalized fields for direct queries

#### alert_history table (Optimized Design)
Tracks all vacancy checks over time
```sql
id (SERIAL) - Primary key
alert_id (INTEGER) - Foreign key to alerts
telegram_id (BIGINT) - Foreign key to users (denormalized for performance)
course_code (VARCHAR) - Course code (denormalized)
index_number (VARCHAR) - Index number (denormalized)
vacancy_count (INTEGER) - Vacancy count at check time
waitlist_count (INTEGER) - Waitlist count at check time
checked_at (TIMESTAMP) - When check occurred
notification_sent (BOOLEAN) - Whether user was notified
```

**Indexes for performance:**
```sql
idx_alert_history_telegram_id - Fast user history queries
idx_alert_history_composite (telegram_id, alert_id, checked_at DESC) - Optimal for trends
idx_alerts_active - Fast active alert lookup
idx_alerts_user - Fast user alert lookup
```

**Migration:** For existing databases, run:
```bash
python migrate_alert_history.py
```

## Prerequisites

- Python 3.8 or higher (recommended: Python 3.13+)
- PostgreSQL 12 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

**Note:** No NTU credentials needed. The bot uses the public vacancy API.

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/jared-makes-stuff/NTU-Vacancy-Alert.git
cd NTU-Vacancy-Alert
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup PostgreSQL Database

Create a new PostgreSQL database:

```bash
# Connect to PostgreSQL
psql -U postgres

# In the PostgreSQL prompt:
CREATE DATABASE ntu_stars_alert;
CREATE USER ntu_bot WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE ntu_stars_alert TO ntu_bot;
\q
```

<details>
<summary>Platform-specific PostgreSQL installation</summary>

**Windows:**
1. Download from https://www.postgresql.org/download/windows/
2. Run installer and follow prompts
3. Remember the password for the `postgres` user

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```
</details>

### 4. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ntu_stars_alert
DB_USER=ntu_bot
DB_PASSWORD=your_secure_password

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Optional: Adjust check interval (seconds)
CHECK_INTERVAL=300  # 5 minutes (default)
```

<details>
<summary>How to get a Telegram Bot Token</summary>

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts to create your bot
4. Copy the bot token (format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Paste it in your `.env` file
</details>

### 5. Initialize Database

```bash
python setup_database.py
```

You should see:
```
Database setup completed successfully!
```

### 6. Run the Bot

```bash
python main.py
```

You should see:
```
NTU STARS Alert Bot is running...
Press Ctrl+C to stop
```

### 7. Use the Bot

1. Open Telegram and find your bot
2. Send `/start`
3. Use `/add` to create vacancy alerts
4. Use `/displayvacancies` to browse without creating alerts

## Bot Commands

### User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Start the bot and register as a user | `/start` |
| `/add` | Create a new vacancy alert | `/add` -> Enter course code -> Select index |
| `/list` | View all your active alerts | `/list` |
| `/remove <ID>` | Remove a specific alert | `/remove 1` |
| `/displayvacancies` | Browse course vacancies without creating alerts | `/displayvacancies` -> Enter course code |
| `/stop` | Deactivate all your alerts permanently | `/stop` |
| `/help` | Show help message with all commands | `/help` |
| `/cancel` | Cancel the current operation | `/cancel` |

### Command Details

#### /add - Create Vacancy Alert
```
You: /add
Bot: Please enter the course code (e.g., CZ2006)
You: CZ2006
Bot: [Shows paginated list of indexes with vacancies]
    
    Index: 10225
    Vacancy: 123
    Waitlist: 0
    Schedule:
       LEC/STUDIO MH3: MON 09:30-11:30
    
    [Previous] [1/3] [Next]
    [Select Index 10225]

You: [Click "Select Index 10225"]
Bot: Alert created! I'll notify you when vacancies open up.
```

**Features:**
- Pagination (5 indexes per page)
- Shows current vacancy/waitlist status
- Displays class schedule
- Navigation with arrow buttons

#### /displayvacancies - Browse Without Alerts
```
You: /displayvacancies
Bot: Please enter the course code to view vacancies
You: CE0001
Bot: [Shows paginated vacancy information]
    No alerts created - just viewing!
```

**Use cases:**
- Check vacancies before deciding to create an alert
- Browse multiple courses quickly
- Share vacancy info with friends

#### /list - View Your Alerts
```
You: /list
Bot: Your Active Alerts (2):

    ID: 1
    Course: CZ2006
    Index: 10225
    Last Vacancy: 3
    Last Checked: 2026-01-02 14:30
    
    ID: 2
    Course: CE0001
    Index: 12345
    Last Vacancy: 0
    Last Checked: 2026-01-02 14:30
```

#### /remove - Delete an Alert
```
You: /remove 1
Bot: Alert 1 has been removed.
```

**Security:**
- You can only remove YOUR OWN alerts
- Alert IDs are scoped per user
- Safe from interference by other users

### How Notifications Work

When a vacancy opens (goes from 0 to 1+), you receive:

```
VACANCY ALERT!

Course: CZ2006
Index: 10225
Vacancies: 3
Waitlist: 0

Hurry! Slots may fill up quickly!

[Register Now] <- Click to go to STARS
```

**Notification Logic:**
- Only sent when `old_vacancy = 0` AND `new_vacancy > 0`
- One notification per vacancy opening
- Tracked in database to prevent spam

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_HOST` | PostgreSQL host | `localhost` | Yes |
| `DB_PORT` | PostgreSQL port | `5432` | Yes |
| `DB_NAME` | Database name | `ntu_stars_alert` | Yes |
| `DB_USER` | Database user | `postgres` | Yes |
| `DB_PASSWORD` | Database password | - | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | - | Yes |
| `CHECK_INTERVAL` | Seconds between vacancy checks | `300` (5 min) | No |
| `LOG_LEVEL` | Logging verbosity | `INFO` | No |

### Adjusting Check Interval

The bot checks vacancies every 5 minutes by default. To change this:

```env
CHECK_INTERVAL=180  # Check every 3 minutes
CHECK_INTERVAL=600  # Check every 10 minutes
```

**Warning:** 
- Don't set this too low to avoid overloading NTU's servers
- Recommended minimum: 120 seconds (2 minutes)
- More frequent checks = higher server load

### Service Hours

The bot respects NTU STARS operating hours:
- **Active:** 8:00 AM - 10:00 PM (Singapore Time, GMT+8)
- **Inactive:** Outside these hours, users get a helpful message

This prevents unnecessary API calls when STARS is unavailable.

### Logging

Change log verbosity in `.env`:

```env
LOG_LEVEL=DEBUG   # Most verbose
LOG_LEVEL=INFO    # Default - recommended
LOG_LEVEL=WARNING # Less verbose
LOG_LEVEL=ERROR   # Only errors
```

Logs are stored in:
- `logs/bot.log` - Bot operations
- `logs/vacancy_checker.log` - Background checks
- `logs/database.log` - Database operations

## Project Structure

```
NTU-Vacancy-Alert/
├── src/
│   ├── __init__.py              # Package initialization
│   ├── bot.py                   # Telegram bot with command handlers (Singleton)
│   ├── config.py                # Configuration management (Singleton)
│   ├── database.py              # PostgreSQL operations (Singleton)
│   ├── logger.py                # Logging setup (Factory pattern)
│   ├── vacancy_api.py           # NTU API client
│   ├── vacancy_checker.py       # Background checker (Singleton)
│   └── vacancy_parser.py        # HTML parser for API responses
├── tests/
│   └── test_vacancy_parser.py   # Parser unit tests (13 tests)
├── logs/                        # Log files (auto-created)
├── references/                  # API documentation
├── main.py                      # Entry point
├── setup_database.py            # Database initialization script
├── migrate_alert_history.py     # Database migration script
├── requirements.txt             # Python dependencies
├── .env.example                 # Example configuration
└── README.md                    # This file
```

### Module Responsibilities

#### bot.py - Telegram Interface
- Command handlers (`/start`, `/add`, `/list`, etc.)
- Conversation state management
- Pagination for large course lists
- User input validation
- Message formatting

**Design Pattern:** Singleton (one bot instance)

#### vacancy_checker.py - Background Monitor
- Fetches all active alerts
- **Groups by (course_code, index_number)** to optimize API calls
- Checks each unique combination once
- Updates all matching alerts
- Sends notifications when vacancies open
- Runs in infinite loop with configurable interval

**Optimization:** O(unique combinations) instead of O(total alerts)

#### vacancy_api.py - API Client
- Makes POST requests to NTU STARS API
- Handles service hours (8am-10pm)
- Error handling with status codes
- Returns structured data

**Endpoints:**
- `get_course_vacancies(course_code)` - Get all indexes for a course
- `get_index_vacancy(course_code, index)` - Get specific index vacancy

#### vacancy_parser.py - HTML Parser
- Uses BeautifulSoup to parse HTML tables
- Extracts vacancy, waitlist, and schedule data
- Handles edge cases (missing data, special characters)
- Fully tested (13 unit tests)

**Separation of Concerns:** Parser logic separated from API client

#### database.py - Data Layer
- User management (create, get, deactivate)
- Alert CRUD operations
- Alert history tracking
- Parameterized queries (SQL injection protection)
- Foreign key relationships

**Design Pattern:** Singleton with connection pooling

#### config.py - Configuration
- Loads environment variables
- Provides defaults
- Validates required settings
- Singleton pattern ensures consistent config

**Design Pattern:** Singleton (one config instance)

### Design Patterns Used

1. **Singleton Pattern**
   - Used by: `Config`, `Database`, `Bot`, `VacancyChecker`
   - Ensures only one instance exists
   - Prevents resource conflicts

2. **Factory Pattern**
   - Used by: `Logger`
   - Creates module-specific loggers
   - Consistent logging configuration

3. **Separation of Concerns**
   - Each module has one responsibility
   - Parser separated from API client
   - Database logic separate from business logic

4. **Conversation State Pattern**
   - Telegram bot uses ConversationHandler
   - States: `ADD_ALERT_COURSE`, `ADD_ALERT_INDEX`, `DISPLAY_VACANCIES_COURSE`
   - Clean user flow management

## Advanced Topics

### Database Migration

If you're upgrading from an older version, run the migration:

```bash
python migrate_alert_history.py
```

This adds denormalized fields to `alert_history` for better query performance.

**What it does:**
1. Adds `telegram_id`, `course_code`, `index_number` columns
2. Populates them from the `alerts` table
3. Creates indexes for fast queries
4. Adds foreign key constraints

**Benefits:**
- Direct user history queries without JOINs
- 10x faster for large datasets
- Enables future `/history` command

### Testing

Run the vacancy parser tests:

```bash
pytest tests/test_vacancy_parser.py -v
```

**Test coverage:**
- Simple HTML parsing
- Multiple indexes
- Class schedules
- Invalid data handling
- Edge cases (empty tables, missing fields)

### API Details

The bot uses NTU's public vacancy checking endpoint:

**Endpoint:**
```
POST https://wish.wis.ntu.edu.sg/webexe/owa/aus_vacancy.check_vacancy2
```

**Request Format:**
```http
Content-Type: application/x-www-form-urlencoded

acadsem=2026;1&r_course_yr=&r_subj_code=CZ2006&r_search_type=F&boption=Search
```

**Response:** HTML table with vacancy data

**Rate Limiting:**
- 2 second delay between unique course/index checks
- Respects service hours (8am-10pm)
- Optimized grouping reduces total requests

**No authentication required** - This is a public endpoint.

### Security Features

- **User Isolation**
  - Users can only access their own alerts
  - Alert IDs scoped per user via `telegram_id`
  - `/remove` command validates ownership

- **SQL Injection Protection**
  - All queries use parameterized statements
  - No raw SQL from user input

- **No Credential Storage**
  - Bot uses public API
  - No NTU passwords stored
  - No encryption needed

- **Data Integrity**
  - Foreign key constraints
  - Cascading deletes (remove user -> remove alerts)
  - Transaction support

## Troubleshooting

### Database Connection Issues

**Error:** `could not connect to server: Connection refused`

**Solutions:**
1. Check if PostgreSQL is running:
   ```bash
   # Windows
   Get-Service postgresql*
   
   # Linux
   sudo systemctl status postgresql
   
   # macOS
   brew services list | grep postgresql
   ```

2. Verify credentials in `.env` match your database:
   ```bash
   psql -h localhost -U ntu_bot -d ntu_stars_alert
   # Enter password when prompted
   ```

3. Check PostgreSQL is listening on the correct port:
   ```bash
   netstat -an | grep 5432
   ```

### Bot Not Responding

**Symptoms:** Bot doesn't reply to commands

**Solutions:**
1. Verify bot token is correct in `.env`
2. Check if bot is running (`python main.py`)
3. Look for errors in `logs/bot.log`
4. Test bot token:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

### No Vacancy Notifications

**Symptoms:** Alerts created but no notifications received

**Checklist:**
1. Check alerts are active: `/list`
2. Verify course/index exists: `/displayvacancies`
3. Check current vacancy is 0 (notifications only when 0->1+)
4. Review `logs/vacancy_checker.log` for errors
5. Ensure `CHECK_INTERVAL` is reasonable (not too high)
6. Confirm current time is 8am-10pm SGT

**Debug mode:**
```env
LOG_LEVEL=DEBUG
```
Restart bot and check logs for detailed information.

### "Module not found" Error

**Error:** `ModuleNotFoundError: No module named 'telegram'`

**Solution:**
```bash
pip install -r requirements.txt
```

If using multiple Python versions:
```bash
python3.13 -m pip install -r requirements.txt
python3.13 main.py
```

### Database Migration Issues

**Error:** Column already exists during migration

**Solution:**
The migration script is idempotent and safe to re-run:
```bash
python migrate_alert_history.py
```

### "Message too long" Error

**Symptoms:** Bot crashes when displaying courses with many indexes

**Status:** Fixed in current version
- Pagination implemented (5 indexes per page)
- Use Previous/Next buttons to navigate

### Performance Issues

**Symptoms:** Slow vacancy checking, high API call count

**Optimizations implemented:**
- Grouping alerts by (course_code, index_number)
- Check unique combinations only once
- 2-second delay between API calls
- Service hour restrictions (8am-10pm)

**Monitor performance:**
```bash
tail -f logs/vacancy_checker.log
```

Look for:
```
Checking 50 alerts...
Grouped into 5 unique course/index combinations
```
If grouped count = total alerts, optimization is not working.

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_vacancy_parser.py -v

# Run with coverage
pytest --cov=src tests/
```

### Code Style

The project follows PEP 8 guidelines:

```bash
# Format code
black src/

# Check linting
flake8 src/

# Type checking (optional)
mypy src/
```

### Adding New Features

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Add tests for new functionality
   - Update documentation
   - Follow existing code patterns

4. **Test your changes**
   ```bash
   pytest
   ```

5. **Submit a pull request**

### Project Conventions

**Naming:**
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_snake_case`

**Logging:**
```python
from .logger import get_logger
logger = get_logger(__name__)

logger.debug("Detailed information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
```

**Database queries:**
```python
# Good - parameterized
cursor.execute("SELECT * FROM alerts WHERE id = %s", (alert_id,))

# Bad - SQL injection risk
cursor.execute(f"SELECT * FROM alerts WHERE id = {alert_id}")
```

## Deployment

### Production Considerations

1. **Use a process manager:**
   ```bash
   # systemd (Linux)
   sudo systemctl enable ntu-stars-bot
   sudo systemctl start ntu-stars-bot
   
   # PM2 (Cross-platform)
   pm2 start main.py --name ntu-stars-bot --interpreter python3
   pm2 save
   pm2 startup
   ```

2. **Database backups:**
   ```bash
   # Backup
   pg_dump ntu_stars_alert > backup_$(date +%Y%m%d).sql
   
   # Restore
   psql ntu_stars_alert < backup_20260102.sql
   ```

3. **Monitor logs:**
   ```bash
   # Rotate logs to prevent disk fill
   logrotate /etc/logrotate.d/ntu-stars-bot
   ```

4. **Environment security:**
   ```bash
   # Restrict .env permissions
   chmod 600 .env
   ```

5. **Health checks:**
   ```bash
   # Check if bot is running
   pgrep -f "python.*main.py"
   
   # Check database connection
   psql -h localhost -U ntu_bot -d ntu_stars_alert -c "SELECT COUNT(*) FROM users;"
   ```

### Scaling Considerations

**Current design supports:**
- Hundreds of users
- Thousands of alerts
- Optimized API calls (grouped checking)

**For larger scale:**
- Add Redis for caching vacancy data
- Implement database connection pooling
- Use message queue for notifications (RabbitMQ, Celery)
- Horizontal scaling with multiple worker processes

## FAQ

**Q: Do I need NTU login credentials?**  
A: No. The bot uses the public NTU STARS vacancy API. No credentials needed.

**Q: How often does the bot check vacancies?**  
A: Every 5 minutes by default. Configurable via `CHECK_INTERVAL` in `.env`.

**Q: Can I monitor courses from different semesters?**  
A: Currently limited to the current semester (automatically detected). Cross-semester support planned.

**Q: Why am I not getting notifications?**  
A: Notifications only sent when vacancy changes from 0 to 1+. If a course already has vacancies, no notification.

**Q: Can multiple users monitor the same course?**  
A: Yes. The bot optimizes by checking each unique course/index only once, regardless of how many users are monitoring it.

**Q: Is my data private?**  
A: Yes. Your alerts are private. Other users cannot see or modify your alerts.

**Q: What happens if the bot crashes?**  
A: All data is safely stored in PostgreSQL. Simply restart the bot - all alerts and history are preserved.

**Q: Can I run this on a free tier server?**  
A: Yes. Works on:
- Heroku free tier (with PostgreSQL addon)
- Railway.app free tier
- Oracle Cloud free tier
- Any VPS with ~512MB RAM

**Q: How do I update to the latest version?**  
A:
```bash
git pull origin main
pip install -r requirements.txt --upgrade
python migrate_alert_history.py  # If needed
python main.py
```

## Contributing

Contributions are welcome! Areas for improvement:

**Features:**
- [ ] `/history` command to show vacancy trends over time
- [ ] Cross-semester alert support
- [ ] Export alerts to CSV
- [ ] Telegram inline query support
- [ ] Multiple notification preferences (Telegram + Email)

**Optimizations:**
- [ ] Redis caching for API responses
- [ ] Database query optimization with connection pooling
- [ ] Rate limiting per user
- [ ] Batch notification sending

**Testing:**
- [ ] Integration tests for bot commands
- [ ] API client tests
- [ ] Database migration tests
- [ ] Load testing

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Ensure all tests pass (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is for **educational purposes only**. 

Please use responsibly and in accordance with:
- NTU's Acceptable Use Policy
- Nanyang Technological University's terms of service
- Telegram's Bot API terms

## Disclaimer

**Important:**
- This bot is **NOT affiliated with or endorsed by** Nanyang Technological University
- Use at your own risk
- The developers are **NOT responsible** for:
  - Missed course registrations
  - Incorrect vacancy information
  - Service interruptions
  - Any issues arising from bot usage

**Fair Usage:**
- Do not spam the NTU API with excessive requests
- Respect the default check interval (5 minutes)
- Report any issues to the maintainers

## Acknowledgments

- **NTU** for providing the public vacancy API
- **python-telegram-bot** library maintainers
- **BeautifulSoup** for HTML parsing
- All contributors and users

## Support

### Getting Help

1. **Check this README** - Most questions answered here
2. **Search existing issues** - Your question may already be answered
3. **Check logs** - `logs/` directory contains detailed error information
4. **Open an issue** - For bugs or feature requests

### Contact

- **GitHub Issues:** [Report bugs or request features](https://github.com/yourusername/NTU-Vacancy-Alert/issues)
- **Discussions:** [Ask questions and share ideas](https://github.com/yourusername/NTU-Vacancy-Alert/discussions)

---

**Made for NTU students**

Star this repo if you find it useful!
