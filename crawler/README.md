# LinkedIn Profile Crawler

Simplified crawler with multiple specialized tools

## File Structure

```
crawler/
├── crawler.py                    # Main crawler class + all helper functions
├── crawler_consumer.py           # RabbitMQ consumer + utilities
├── crawler_manager.py            # NEW: Manages crawler lifecycle based on schedules
├── crawler_search.py             # Search profiles by name
├── crawler_search_consumer.py    # RabbitMQ consumer for search jobs
├── scheduler_daemon.py           # Scheduled crawl job executor
├── test_search.py                # Quick test for single profile search
├── .env                          # Configuration
├── requirements.txt              # Dependencies
├── helper/
│   ├── supabase_helper.py       # Supabase integration for storing leads
│   └── rabbitmq_helper.py       # RabbitMQ queue management
└── data/
    ├── cookie/                  # LinkedIn session cookies
    ├── output/                  # Scraped profiles (JSON)
    └── search_input_example.json  # Example input for search crawler
```

## Features

- **All-in-one design**: Core crawler with modular helpers
- **Profile search by name**: Search LinkedIn profiles by name and extract URLs
- **Queue-based search processing**: Multi-worker RabbitMQ consumer for parallel search jobs
- **Automated crawler lifecycle management**: NEW - Start/stop crawler based on database schedules
- **Supabase integration**: Direct storage to `leads_list` table with duplicate prevention
- **Browser restart**: Prevents memory leak every N profiles
- **Mobile/Desktop mode**: Choose scraping mode
- **Anti-detection**: Random delays, human-like scrolling
- **Cookie persistence**: Login once, reuse session
- **Duplicate prevention**: Skip already crawled profiles
- **RabbitMQ integration**: Queue-based processing
- **Scoring integration**: Auto-send to scoring queue

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure `.env`:
```bash
cp .env.example .env
# Edit .env with your LavinMQ credentials
# See LAVINMQ-SETUP.md for detailed setup guide
```

3. Test LavinMQ connection:
```bash
cd ../..
python test-lavinmq.py
```

## Usage

### Profile Search by Name (NEW)
Search LinkedIn profiles by name and extract URLs:

```bash
# Quick test - search single profile
python test_search.py "Vika Vitaloka Pramansah"

# RECOMMENDED: Automatic mode - Send to queue + start workers
python crawler_search.py data/names.json

# Manual mode: Send jobs to queue only
python crawler_search.py --send data/names.json

# Manual mode: Start workers only (process queued jobs)
python crawler_search.py --queue
```

**Automatic Mode (Recommended)**:
The default mode automatically sends all search jobs to the RabbitMQ queue and starts worker threads to process them in parallel. This is the simplest way to process large batches of names.

**Manual Mode**:
For more control, you can separate the send and consume operations:
1. Send jobs to queue: `python crawler_search.py --send data/names.json`
2. Start workers separately: `python crawler_search.py --queue`

**Note**: As of the latest update, `crawler_search.py` now includes RabbitMQ integration support with queue configuration constants (`SEARCH_QUEUE` and `MAX_WORKERS`). These are primarily used by `crawler_search_consumer.py` for queue-based processing, but the constants are defined in the base search module for consistency.

**Input format** (`data/search_input.json`):
```json
[
  {
    "template_id": "8191cb53-725e-46f5-a54a-79affc378811",
    "name": "Vika Vitaloka Pramansah",
    "profile_url": "https://www.linkedin.com/in/vika-vitaloka-pramansah-a74350188/"
  },
  {
    "template_id": "8191cb53-725e-46f5-a54a-79affc378811",
    "name": "Deanira Maharani",
    "profile_url": null
  }
]
```

**Note**: The repository includes a production dataset at `data/search_input.json` with 93 profiles ready for processing. This file contains real profile data with template ID `8191cb53-725e-46f5-a54a-79affc378811`. All profiles in the current dataset have existing LinkedIn URLs populated - no URL discovery needed.

**Note**: The `template_id` field is required to link search results to specific requirement templates. The crawler will search for profiles and populate the `profile_url` field automatically.

**Output format**:
```json
[
  {
    "template_id": "8191cb53-725e-46f5-a54a-79affc378811",
    "name": "Vika Vitaloka Pramansah",
    "profile_url": "https://www.linkedin.com/in/username"
  },
  {
    "template_id": "8191cb53-725e-46f5-a54a-79affc378811",
    "name": "Deanira Maharani",
    "profile_url": null
  }
]
```

**Note**: As of the latest update, the output field has been renamed from `linkedin_url` to `profile_url` for consistency with other crawler components. The `template_id` field is preserved in the output to maintain the link to requirement templates.

**Features**:
- Searches LinkedIn using global search
- Extracts first profile URL from results
- Random delay 3-7 seconds between searches
- Handles no results, timeouts, redirects
- Sets `profile_url` to `null` if not found

**See detailed documentation**: [SEARCH_README.md](SEARCH_README.md)

### Profile Search Consumer (Queue-Based Processing)
Process search jobs from RabbitMQ queue with multiple parallel workers:

```bash
python crawler_search_consumer.py
```

**Features**:
- Multi-worker architecture for parallel processing
- RabbitMQ queue integration for job distribution
- Automatic browser session management per worker
- Statistics tracking (found, not found, errors)
- Optional result queue for downstream processing
- Graceful error handling and worker isolation

**Configuration** (`.env`):
```bash
SEARCH_QUEUE=linkedin_search_queue  # Queue name for search jobs
SEARCH_MAX_WORKERS=3                # Number of parallel workers (default: 3)
```

**Job Format** (send to queue):
```json
{
  "job_id": "search-001",
  "name": "John Doe",
  "result_queue": "search_results"  // Optional: queue to send results
}
```

**Result Format** (sent to result_queue if specified):
```json
{
  "job_id": "search-001",
  "name": "John Doe",
  "profile_url": "https://www.linkedin.com/in/johndoe",
  "status": "found"  // or "not_found", "error"
}
```

**Note**: The result field has been updated from `linkedin_url` to `profile_url` for consistency across the crawler system.

**How It Works**:
1. Each worker connects to RabbitMQ and waits for jobs
2. RabbitMQ distributes jobs across workers using round-robin
3. Worker initializes browser session (reused across jobs)
4. Worker searches LinkedIn for the profile
5. Result is acknowledged and optionally sent to result queue
6. Worker processes next job (with rate limiting delays)

**Worker Statistics**:
Each worker tracks:
- `processed`: Total jobs processed
- `found`: Profiles successfully found
- `not_found`: Profiles not found
- `errors`: Failed searches

**Starting Workers**:
```bash
python crawler_search_consumer.py
```

Output:
```
============================================================
LINKEDIN PROFILE SEARCH CONSUMER
============================================================
Queue: linkedin_search_queue
Workers: 3
============================================================

[Worker 1] Starting...
[Worker 1] ✓ Connected to RabbitMQ
[Worker 2] Starting...
[Worker 2] ✓ Connected to RabbitMQ
[Worker 3] Starting...
[Worker 3] ✓ Connected to RabbitMQ

✓ All 3 workers started!

💡 How it works:
  1. Workers wait for search jobs in queue
  2. Each worker processes 1 job at a time
  3. Multiple workers run in parallel
  4. Results can be sent to result queue (optional)

  Press Ctrl+C to stop all workers
```

**Use Cases**:
- Bulk profile URL discovery from name lists
- Integration with other services via result queue
- Parallel processing of large search batches
- Automated lead generation pipelines

**Comparison with Direct Search**:
- **Direct (`crawler_search.py`)**: Best for small batches, JSON file processing, one-off searches
- **Consumer (`crawler_search_consumer.py`)**: Best for continuous processing, service integration, high-volume searches

### Scheduler Daemon (Production)
Run scheduled crawl jobs from Supabase:

```bash
python scheduler_daemon.py
```

Features:
- Polls Supabase for active schedules
- Executes crawl jobs based on schedule timing
- Saves profiles directly to `leads_list` table
- Updates `last_run` timestamp automatically
- Configurable poll interval via `POLL_INTERVAL` env var
- **Smart profile sourcing with fallback priority**
- **Duplicate detection and skip logic**
- **Update existing leads instead of creating duplicates**

The daemon uses a priority-based approach to find profiles to scrape:

**Priority 1: JSON File (if linked)**
- If schedule has a `file_id`, loads profile URLs from the linked JSON file in `crawler_jobs` table
- Extracts URLs from the JSON data structure

**Priority 2: Unscraped Profiles from Supabase**
- If no JSON file is linked, automatically queries `leads_list` table for unscraped profiles
- Finds profiles where `profile_data` is null or empty
- Limits to 100 profiles per execution (configurable)
- Enables continuous scraping of new leads added to the database

**Duplicate Prevention:**
- Before scraping, checks if profile already has `profile_data` in database
- Skips profiles that are already scraped (non-empty `profile_data`)
- Updates existing leads instead of creating duplicates
- Tracks skipped count in execution statistics

The daemon workflow:
1. Checks for active schedules every 5 minutes (default)
2. Executes schedules that haven't run in the last hour
3. Sources profile URLs using priority system (JSON file → Unscraped profiles)
4. For each profile URL:
   - Checks if already scraped (has `profile_data`)
   - Skips if already scraped
   - Scrapes profile if not yet scraped
   - Updates existing lead or inserts new lead
5. Saves results to Supabase `leads_list` table with:
   - `profile_url`: LinkedIn profile URL
   - `name`: Extracted from profile data
   - `profile_data`: Full JSON profile data
   - `connection_status`: Set to 'scraped'
   - `date`: Current date (for new leads only)
6. Reports statistics: Success count, Skipped count, Failed count

### Crawler Manager (NEW - Automated Lifecycle Management)
Automatically start and stop the crawler consumer based on database schedules:

```bash
python crawler_manager.py
```

**What It Does:**
The Crawler Manager monitors your Supabase `crawler_schedules` table and automatically starts/stops the crawler consumer process based on the schedule's start and stop times. This eliminates the need to manually manage crawler processes.

**Features:**
- **Automatic process management**: Starts `crawler_consumer.py` when schedules are active
- **Graceful shutdown**: Stops crawler when no schedules are active
- **Health monitoring**: Detects if crawler process dies and restarts if needed
- **Cron-based scheduling**: Supports standard cron expressions for start/stop times
- **Weekday filtering**: Run crawlers only on specific days (e.g., weekdays only)
- **Time-based control**: Start at 9 AM, stop at 5 PM automatically
- **Single schedule priority**: Uses first active schedule if multiple are running

**How It Works:**
1. Polls Supabase every 60 seconds (configurable via `POLL_INTERVAL`)
2. Checks which schedules should be running based on current time
3. Compares schedule's `start_schedule` and `stop_schedule` cron expressions
4. Starts crawler if schedule is active and crawler is not running
5. Stops crawler if no schedules are active and crawler is running
6. Monitors crawler health and restarts if process dies unexpectedly

**Cron Expression Support:**
The manager supports simplified cron expressions in the format:
```
minute hour day month weekday
```

**Examples:**
- `0 9 * * *` - Every day at 9:00 AM
- `0 9 * * 1-5` - Weekdays (Mon-Fri) at 9:00 AM
- `30 8 * * *` - Every day at 8:30 AM
- `0 17 * * 1-5` - Weekdays at 5:00 PM (for stop_schedule)

**Schedule Configuration:**
In your `crawler_schedules` table:
- `start_schedule`: Cron expression for when to start crawler (e.g., `0 9 * * 1-5`)
- `stop_schedule`: Cron expression for when to stop crawler (e.g., `0 17 * * 1-5`)
- `status`: Must be `active` for manager to consider the schedule

**Example Schedule:**
```sql
INSERT INTO crawler_schedules (name, start_schedule, stop_schedule, status)
VALUES ('Weekday Crawler', '0 9 * * 1-5', '0 17 * * 1-5', 'active');
```
This runs the crawler Monday-Friday from 9 AM to 5 PM.

**Process Management:**
- **Graceful shutdown**: Sends SIGTERM and waits up to 30 seconds
- **Force kill**: If graceful shutdown fails, forces process termination
- **Health checks**: Monitors process status every poll interval
- **Auto-restart**: Restarts crawler if it dies unexpectedly during active schedule

**Configuration (`.env`):**
```bash
POLL_INTERVAL=60  # Check schedules every 60 seconds (default)
```

**Output Example:**
```
============================================================
CRAWLER MANAGER STARTED
Poll Interval: 60 seconds
Python: /usr/bin/python3
Crawler Script: crawler_consumer.py
============================================================

Schedule active: Weekday Crawler
Starting crawler consumer for schedule: abc-123-def
✓ Crawler consumer started (PID: 12345)
Crawler running (Schedule: abc-123-def)
...
No active schedules, stopping crawler
Stopping crawler consumer...
✓ Crawler consumer stopped
```

**Use Cases:**
- **Business hours crawling**: Run crawler only during work hours
- **Weekday-only operations**: Avoid weekend crawling
- **Resource optimization**: Stop crawler when not needed to save resources
- **Automated operations**: Set-and-forget crawler management
- **Multiple schedule support**: Different schedules for different time windows

**Timezone Support:**
- **UTC-based scheduling**: All schedule calculations use UTC timezone for consistency
- **Cross-timezone compatibility**: Works reliably across different server timezones
- **Daylight saving time handling**: UTC prevents DST-related scheduling issues

**Comparison with Scheduler Daemon:**
- **Scheduler Daemon**: Executes crawl jobs at specific times (one-time or periodic execution)
- **Crawler Manager**: Manages crawler consumer lifecycle (continuous operation during time windows)

### Consumer Mode (Recommended)
Process URLs from `profile/*.json` files with RabbitMQ:

```bash
python crawler_consumer.py
```

Features:
- Auto-load URLs from profile folder
- Skip already crawled profiles
- Skip sales URLs
- Multi-worker processing
- Send to scoring queue
- Supabase integration (automatic save to `leads_list` table)

### Direct Import
Use crawler directly in your code:

```python
from crawler import LinkedInCrawler
from helper.supabase_helper import SupabaseManager

# Initialize
crawler = LinkedInCrawler()
supabase = SupabaseManager()

# Login and scrape
crawler.login()
profile_data = crawler.get_profile("https://linkedin.com/in/username")

# Save to Supabase
supabase.save_lead(
    profile_url=profile_data['profile_url'],
    name=profile_data['name'],
    profile_data=profile_data,
    connection_status='scraped'
)

crawler.close()
```

## Supabase Helper

The `SupabaseManager` class provides methods for storing and managing leads:

### Methods

**`save_lead(profile_url, name, profile_data, connection_status='scraped', template_id=None)`**
- Saves or updates a lead in the `leads_list` table
- Automatically handles duplicates (updates existing, inserts new)
- Stores complete profile data in JSONB column
- Optional `template_id` parameter for filtering leads by requirement template
- Returns: `bool` (success status)

**`update_connection_status(profile_url, status)`**
- Updates the connection status for a lead
- Common statuses: `scraped`, `connection_sent`, `message_sent`, `connected`
- Returns: `bool` (success status)

**`lead_exists(profile_url)`**
- Checks if a lead already exists in the database
- Returns: `bool`

**`get_lead(profile_url)`**
- Retrieves complete lead data from database
- Returns: `dict` or `None`

**`update_lead_after_scrape(profile_url, profile_data)`**
- Updates or inserts a lead after scraping profile data
- Automatically extracts name from profile_data
- Sets connection_status to 'scraped'
- Updates existing lead or inserts new lead if not found
- Adds processed_at timestamp
- Returns: `bool` (success status)

### Usage Example

```python
from helper.supabase_helper import SupabaseManager

supabase = SupabaseManager()

# Check if lead exists
if not supabase.lead_exists("https://linkedin.com/in/username"):
    # Save new lead with optional template_id
    supabase.save_lead(
        profile_url="https://linkedin.com/in/username",
        name="John Doe",
        profile_data={...},
        connection_status='scraped',
        template_id='abc-123-def'  # Optional: link to requirement template
    )

# Update status after sending connection
supabase.update_connection_status(
    profile_url="https://linkedin.com/in/username",
    status='connection_sent'
)

# Retrieve lead data
lead = supabase.get_lead("https://linkedin.com/in/username")
if lead:
    print(f"Lead: {lead['name']}, Status: {lead['connection_status']}")
    if lead.get('template_id'):
        print(f"Template: {lead['template_id']}")
```

## Configuration

Edit `.env` file:

```bash
# LinkedIn Credentials (for email/password login)
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword

# OAuth Login (for Google/Microsoft/Apple login)
USE_OAUTH_LOGIN=false  # Set to true if using OAuth

# Delays (seconds)
MIN_DELAY=2.0
MAX_DELAY=5.0
PROFILE_DELAY_MIN=10.0
PROFILE_DELAY_MAX=20.0

# Mode
USE_MOBILE_MODE=false

# Headle

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# RabbitMQ - Option 1: CloudAMQP URL (recommended for cloud deployments)
CLOUDAMQP_URL=amqps://user:pass@host.lmq.cloudamqp.com/vhost

# RabbitMQ - Option 2: Individual settings (for local/custom setups)
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
RABBITMQ_QUEUE=linkedin_profiles

# SSL/TLS Support
# Port 5671 automatically enables SSL/TLS connection
# Port 5672 uses standard non-encrypted connection

# Scoring
SCORING_QUEUE=scoring_queue
DEFAULT_REQUIREMENTS_ID=desk_collection

# Scheduler Daemon
POLL_INTERVAL=300  # Check for schedules every 5 minutes

# Outreach Workers
MAX_WORKERS=3  # Number of parallel outreach workers (default: 3)

# Search Consumer
SEARCH_QUEUE=linkedin_search_queue  # Queue name for search jobs
SEARCH_MAX_WORKERS=3                # Number of parallel search workers (default: 3)
```

### RabbitMQ Configuration Options

The crawler supports two ways to configure RabbitMQ:

**Option 1: CloudAMQP URL (Recommended for Cloud)**
```bash
CLOUDAMQP_URL=amqps://username:password@host.lmq.cloudamqp.com/vhost
```
- Automatically parses connection details from URL
- Supports both `amqp://` (plain) and `amqps://` (SSL/TLS)
- SSL is auto-enabled for `amqps://` URLs
- Perfect for LavinMQ, CloudAMQP, or other managed services

**Option 2: Individual Environment Variables**
```bash
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_VHOST=/
```
- Use for local RabbitMQ instances
- SSL auto-enabled if port is 5671
- Falls back to this if `CLOUDAMQP_URL` is not set

### OAuth Login Setup

Jika akun LinkedIn Anda menggunakan OAuth (Google/Microsoft/Apple):

1. Set di `.env`:
```bash
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=
USE_OAUTH_LOGIN=true
```

2. Jalankan crawler:
```bash
python crawler_consumer.py
```

3. Browser akan terbuka, login manual dengan OAuth
4. Cookie tersimpan otomatis di `data/cookie/.linkedin_cookies.json`
5. Login berikutnya otomatis menggunakan cookie

**Lihat panduan lengkap**: [OAUTH_LOGIN.md](OAUTH_LOGIN.md)

### Cookie Management

Kelola cookie dengan script helper:

```bash
# Interactive menu
python manage_cookies.py

# Or direct commands
python manage_cookies.py check    # Check cookie status
python manage_cookies.py backup   # Backup cookies
python manage_cookies.py restore  # Restore from backup
python manage_cookies.py delete   # Delete cookies
```

## How It Works

**crawler.py** contains:
- `LinkedInCrawler` class
- Browser helper functions (create_driver, delays, scrolling)
- Auth helper functions (login, cookies)
- Extraction helper functions (show all, navigation)

**crawler_consumer.py** contains:
- `RabbitMQManager` class
- Consumer worker threads
- Profile save utilities
- Scoring integration
- Supabase integration (automatic save to database)

**crawler_search.py** contains:
- `LinkedInSearchCrawler` class
- Profile search by name functionality
- JSON file processing utilities
- Search result extraction and validation
- RabbitMQ integration support (queue configuration constants)
- Multi-threading support for parallel processing

**crawler_search_consumer.py** contains:
- `SearchConsumer` class for job processing
- Multi-worker thread management
- RabbitMQ queue integration for search jobs
- Statistics tracking per worker
- Optional result queue support

**scheduler_daemon.py** contains:
- Supabase schedule polling
- Scheduled job execution
- Direct `leads_list` table integration
- Automatic last_run tracking
- **Intelligent profile sourcing with priority fallback**
- **Duplicate detection and prevention**
- **Automatic unscraped profile discovery**

## Monitoring

RabbitMQ Management UI: http://localhost:15672
- Login: `guest` / `guest`

## Consumer Mode Statistics

The crawler consumer tracks the following metrics:
- `processing`: Currently processing profiles
- `completed`: Successfully scraped profiles
- `failed`: Failed scraping attempts
- `skipped`: Profiles skipped (already crawled or sales URLs)
- `sent_to_scoring`: Profiles sent to scoring queue
- `saved_to_supabase`: Profiles saved to Supabase database
- `supabase_failed`: Failed Supabase save attempts

Each worker automatically:
1. Connects to Supabase on startup (gracefully continues without it if connection fails)
2. Scrapes the LinkedIn profile
3. ~~Saves profile data to local JSON file (`data/output/`)~~ **DISABLED** - Local file saving is now disabled to reduce disk usage
4. Saves profile data to Supabase `leads_list` table with:
   - `profile_url`: LinkedIn profile URL
   - `name`: Extracted from profile data
   - `profile_data`: Complete JSON profile data
   - `connection_status`: Set to 'scraped'
5. Sends profile data to scoring queue for processing

**Note**: As of the latest update, local JSON file backups are disabled. All profile data is stored exclusively in Supabase. This reduces disk usage and simplifies data management. The `save_profile_data()` function remains available in the codebase but is commented out in the consumer workflow.

## Output

**Note**: Local JSON file saving has been disabled in the consumer workflow. Profile data is now stored exclusively in Supabase.

~~JSON files saved to: `data/output/`~~

The `data/output/` directory may still contain historical profile data from previous runs, but new profiles are no longer saved locally. All profile data is stored in the Supabase `leads_list` table with the following structure in the `profile_data` JSONB column:

```json
{
  "profile_url": "...",
  "name": "...",
  "location": "...",
  "gender": "...",
  "estimated_age": {...},
  "about": "...",
  "experiences": [...],
  "education": [...],
  "skills": [...],
  "projects": [...],
  "honors": [...],
  "languages": [...],
  "licenses": [...],
  "courses": [...],
  "volunteering": [...],
  "test_scores": [...]
}
```

## Docker Testing

Test the Docker build locally before deploying to production:

```bash
./test-docker.sh
```

This script will:
- Build the Docker image locally
- Validate the build process
- Start a test container with your `.env` configuration
- Stream container logs for monitoring
- Automatically cleanup on exit

**Requirements:**
- Docker installed and running
- `.env` file with required credentials (LINKEDIN_EMAIL, LINKEDIN_PASSWORD, RABBITMQ_HOST, etc.)

**Note:** First build downloads Chrome (~500MB) and may take 5-10 minutes.

## Troubleshooting

**RabbitMQ SSL Connection:**
- Port 5671 automatically enables SSL/TLS encryption
- Port 5672 uses standard non-encrypted connection
- SSL is auto-detected based on port number
- Connection logs show SSL status: `Connected to RabbitMQ at host:port (SSL: True/False)`
- For LavinMQ cloud instances, use port 5671 with SSL

**ChromeDriver not found:**
```bash
pip install webdriver-manager
```

**Login verification required:**
- Complete verification in browser
- Press ENTER in terminal after login
- Cookies will be saved for next time

**Memory leak / data becomes empty:**
- Browser restarts automatically every 10 profiles
- This prevents memory leak and keeps accuracy high

**Docker build fails:**
- Ensure Docker is running
- Check `.env` file exists with all required variables
- Try `docker system prune` to free up space

**Outreach: Connect button not found:**
- The system now automatically tries the More dropdown menu if direct Connect button is not found
- Check debug screenshots in `data/output/outreach_screenshots/debug_no_connect_*.png`
- Review HTML page source saved alongside screenshots for detailed inspection
- LinkedIn UI may have changed - verify button exists on profile page or in More menu
- Ensure profile is not already connected (system now double-checks for "Message" button)
- Page automatically scrolls to top and waits 20 seconds for content to load
- Check console logs for which selectors were attempted and their results
- The `find_connect_button()` function handles both direct buttons and dropdown menus automatically

## Outreach Testing

Test the automated outreach functionality before sending real connection requests:

```bash
python test_outreach.py
```

This script allows you to:
- Send test outreach jobs to the RabbitMQ queue
- Verify the outreach worker processes jobs correctly
- Test message personalization with `{lead_name}` placeholder
- Run in dry-run mode (no actual connection requests sent)

**Before running:**
1. Ensure LavinMQ is configured in `.env` (see LAVINMQ-SETUP.md)
2. Test connection: `python ../../test-lavinmq.py`
3. Edit `test_outreach.py` to customize the test job:
   - `name`: Lead's name for personalization
   - `profile_url`: LinkedIn profile URL
   - `message`: Connection request message template
   - `dry_run`: Set to `True` for testing (no real send), `False` for production

**Configuration in `.env`:**
```bash
OUTREACH_QUEUE=outreach_queue  # Queue name for outreach jobs

# Supabase Configuration (for outreach tracking)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

**After sending test job:**
```bash
python crawler_outreach.py  # Start the outreach worker(s) to process the job
```

### Multi-Worker Architecture

The outreach system now supports parallel processing with multiple worker threads:

**Configuration:**
```bash
# Set number of workers in .env (default: 3)
MAX_WORKERS=3
```

**How It Works:**
- Each worker runs in a separate thread and processes jobs independently
- RabbitMQ distributes jobs across workers using round-robin
- Each worker maintains its own browser session and rate limiting
- Workers process 1 job at a time with 90-second delays between jobs
- Combined throughput: ~40 requests/hour per worker (e.g., 3 workers = ~120 requests/hour)

**Starting Workers:**
```bash
python crawler_outreach.py
```

Output:
```
============================================================
LINKEDIN AUTOMATED OUTREACH WORKER
============================================================
Queue: outreach_queue
============================================================

→ Number of workers: 3
→ Queue: outreach_queue
→ Rate limit: 90 seconds between jobs per worker
→ Throughput: ~120 requests/hour with 3 workers

→ Starting 3 outreach workers...
[Worker 1] Started
[Worker 1] ✓ Connected to RabbitMQ
[Worker 2] Started
[Worker 2] ✓ Connected to RabbitMQ
[Worker 3] Started
[Worker 3] ✓ Connected to RabbitMQ

✓ All 3 workers are running!

💡 How it works:
  1. Each worker processes 1 job at a time
  2. Multiple workers run in parallel
  3. RabbitMQ distributes jobs across workers
  4. Each worker waits 90 seconds between jobs

  Press Ctrl+C to stop all workers
```

**Worker Logs:**
Each worker prefixes its logs with `[Worker N]` for easy identification:
```
[Worker 1] 📥 NEW JOB RECEIVED
[Worker 1] Job ID: test-01
[Worker 1] Lead: John Doe
[Worker 1] URL: https://linkedin.com/in/johndoe
[Worker 1] Mode: 🧪 DRY RUN (testing)
...
[Worker 1] ✓ Updated
[Worker 1] ⏳ Waiting 90 seconds before next job (rate limiting)...
```

**Scaling Considerations:**
- **Conservative (Recommended)**: 1-2 workers with 90-second delays (~40-80 requests/hour)
- **Moderate**: 3 workers with 90-second delays (~120 requests/hour)
- **Aggressive**: 5+ workers with 60-second delays (~300+ requests/hour) - ⚠️ High risk of rate limiting

**Stopping Workers:**
- Press `Ctrl+C` to stop all workers gracefully
- Workers will finish their current tasks before stopping
- Unprocessed jobs remain in the queue for next startup

The worker will:
- Navigate to the profile
- Click Connect button (with improved selector detection)
- Add a personalized note
- Type the message with human-like behavior
- Take a screenshot for verification
- In dry-run mode: Close modal without sending
- In production mode: Send actual connection requests (controlled by `dry_run` flag in job payload)

**Recent Improvements (Latest - Feb 24, 2026):**
- **Improved Dropdown "Remove Connection" Detection (Feb 24, 2026 - Latest)**: Refined dropdown menu handling for better reliability
  - **Integrated detection** - "Remove connection" detection now integrated into main dropdown search loop
  - **Early detection during iteration** - Checks each dropdown element for "Remove connection" before validating as Connect button
  - **Dual validation** - Checks both element text and aria-label for "remove" + "connection" keywords
  - **Immediate return** - Returns `"ALREADY_CONNECTED"` marker as soon as "Remove connection" is detected
  - **Prevents false positives** - Validates element is actually displayed before triggering detection
  - **Cleaner code flow** - Removed separate pre-validation check, now part of unified dropdown element iteration
  - **Detailed logging** - Logs when "Remove connection" is found in text or aria-label with clear status messages
  - **Safety feature** - Never clicks the "Remove connection" button, only detects its presence
  - **Database update** - Properly updates lead status with note indicating already connected
- **Message Button Detection Temporarily Disabled (Feb 24, 2026)**: Strategy 4 (Message button detection) has been temporarily disabled for testing
  - **Testing phase** - Disabled to evaluate impact on connection detection accuracy
  - **Code commented out** - All Message button detection logic is preserved but commented out in `send_connection_request()`
  - **Other strategies remain active**:
    - Strategy 1: Global Pending button detection
    - Strategy 2: Aria-label detection for pending status
    - Strategy 3: "Remove connection" button detection
    - Strategy 5: Dropdown "Remove connection" detection (in `find_connect_button()`)
  - **To re-enable** - Uncomment lines 423-437 in `crawler_outreach.py`
  - **Reason for testing** - Evaluating whether Message button detection causes false positives or if it's necessary for accurate connection status tracking
- **Scoped Message Button Detection (Feb 24, 2026 - Currently Disabled)**: Enhanced Strategy 4 to prevent false positives from ads and recommendations
  - **Profile header scoping** - Message button detection now limited to profile action areas only
  - **Targeted XPath selectors** - Uses `pvs-sticky-header-profile-actions` and `pv-top-card-v2-ctas` classes to scope search
  - **Prevents false positives** - Eliminates detection of Message buttons from:
    - LinkedIn ads and sponsored content
    - "People Also Viewed" recommendations
    - Activity feed items
    - Other non-profile sections
  - **Improved reliability** - Only detects Message button in actual profile header, ensuring accurate connection status
  - **Clearer logging** - Updated log message to indicate "Message button found in profile header"
  - **⚠️ Currently disabled for testing** - See "Message Button Detection Temporarily Disabled" above
- **Cleaner Logging & Production-Ready Detection (Feb 24, 2026)**: Streamlined logging output for production use while maintaining reliability
  - **Removed verbose debug output** - Eliminated detailed button enumeration and excessive logging that cluttered production logs
  - **Simplified status messages** - Clean, concise logging that focuses on detection results rather than process details
  - **Removed Strategy 5** - Eliminated "Send profile in a message" detection as it was redundant with other strategies
  - **Core detection strategies remain unchanged**:
    - **Strategy 1**: Global Pending button detection via `//button[.//span[normalize-space()='Pending']]`
    - **Strategy 2**: Aria-label detection (case-insensitive) for pending status
    - **Strategy 3**: "Remove connection" button detection for already-connected profiles
    - **Strategy 4**: "Message" button detection as secondary connection indicator (⚠️ **TEMPORARILY DISABLED FOR TESTING**)
  - **Maintained reliability features**:
    - 2-second page render wait before status checks
    - All strategies return success status to prevent duplicate tracking
    - Database updates on detection with appropriate notes
    - Early return on detection to stop processing immediately
    - Graceful error handling with warning logs
  - **Production benefits**: Cleaner logs make monitoring easier and reduce noise in production environments
- **MAJOR UPDATE: Simplified & Enhanced Pending Detection (Feb 24, 2026)**: Streamlined detection system with global search
  - **Removed profile header scoping** - Now searches entire page for better reliability
  - **Strategy 1: Global Pending button detection** - Searches for `<button>` with `<span>` containing "Pending"
    - Uses strong XPath: `//button[.//span[normalize-space()='Pending']]`
    - Searches entire page (not limited to header) to catch all pending states
    - Returns `pending_success` when visible Pending button found
  - **Strategy 2: Aria-label detection (case-insensitive)** - Searches for buttons with aria-label containing "pending"
    - Uses XPath `translate()` function for case-insensitive matching
    - Fallback for buttons where text is in aria-label instead of span
    - Returns `pending_success` when visible button found
  - **Strategy 3: "Remove connection" detection** - Detects already-connected profiles
    - Searches for button text or aria-label containing "Remove connection"
    - Returns `already_connected_success` status when found
  - **Strategy 4: "Message" button detection** - ⚠️ **TEMPORARILY DISABLED FOR TESTING**
    - Previously used `normalize-space(text())='Message'` for exact matching
    - Was designed to return `already_connected_success` status when found
    - Currently commented out to evaluate impact on detection accuracy
  - **All strategies return success status** - Treated as successful operation to prevent duplicate tracking
  - **Database update on detection** - Updates lead with appropriate note for each status
  - **Early return on detection** - Stops processing immediately when status is found
  - **Graceful error handling** - Continues with connection attempt if status check fails (with warning logged)
- **Enhanced connection status detection with multiple strategies (Feb 24, 2026)**: Comprehensive detection system to prevent duplicate connection attempts
  - **Strategy 1: "Remove connection" button detection** - Primary indicator of already-connected profiles
    - Searches for button text or aria-label containing "Remove connection"
    - Returns `already_connected_success` status when found
    - Updates database with note indicating already connected
  - **Strategy 2: "Message" button detection** - Secondary indicator of existing connections
    - Uses `normalize-space(text())='Message'` for exact matching
    - Checks both aria-label and exact text match
    - Returns `already_connected_success` status when found
  - **Strategy 3: "Send profile in a message" detection** - Fallback indicator for connected/pending profiles
    - Searches for "Send profile in a message" option (appears when already connected or pending)
    - Returns `already_connected_success` status when found
  - **Improved profile header detection**: Added `pvs-sticky-header-profile-actions` selector for better reliability
  - **Detailed logging**: Each detection strategy logs its progress and results for debugging
  - **Graceful error handling**: Continues with connection attempt if status check fails (with warning logged)
  - **Scoped search**: All searches limited to profile header container to prevent false positives
- **CRITICAL SAFETY FIX - Strict Connect button validation (UPDATED)**: Enhanced validation now applies to BOTH direct buttons AND dropdown menu items
  - **Exact text matching**: Button text must be EXACTLY "Connect" (case-insensitive, normalized whitespace)
  - **Dangerous keyword filtering**: Rejects buttons containing: 'remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect'
  - **Double validation**: Checks both button text AND aria-label attribute for dangerous keywords
  - **XPath normalization**: Uses `normalize-space()` to handle whitespace variations
  - **Explicit rejection logging**: Logs skipped buttons with their text for debugging
  - **Safety-first approach**: Only proceeds if button text is exactly "connect" after all checks
  - **NEW: Dropdown menu validation**: Same strict validation now applied to dropdown items
    - Validates text is EXACTLY "connect" (not "connection", "disconnect", etc.)
    - OR validates aria-label contains "invite" + "connect" + "to connect" (LinkedIn's pattern)
    - Prevents accidental clicks on "Remove connection" or "Withdraw invitation" in dropdown
    - Detailed logging shows why each button was accepted or rejected
- **Refined Connect button detection logic**: Improved reliability and debugging for both direct and dropdown scenarios
  - **Profile header detection**: Added `pvs-sticky-header-profile-actions` selector for better header container identification
  - **Direct Connect button search**: Now only attempts if profile header is found, preventing unnecessary searches
  - **More button location validation**: Checks button Y-coordinate to ensure it's in top 1000px of page (prevents clicking wrong buttons in recommendations)
  - **Enhanced More button selectors**: Added profile-specific selectors targeting `pvs-sticky-header-profile-actions` area first
  - **Increased dropdown wait time**: Extended from 2 to 3 seconds for dropdown animation to complete
  - **Detailed progress logging**: Added numbered selector attempts (e.g., "Trying More selector 1/5...") for easier debugging
  - **Element count reporting**: Logs how many elements were found for each selector before filtering
  - **Aria-label preview**: Shows first 50 characters of aria-label when checking dropdown elements
  - **Improved error messages**: Each selector failure now logs with specific error details
- **Enhanced dropdown menu handling (Feb 2026)**: Significantly improved reliability when Connect button is in More dropdown
  - Explicit wait for dropdown menu to appear after clicking More button (with timeout handling)
  - Waits for `div[@role='menu']` or `artdeco-dropdown__content` elements to be present
  - Additional 1-second delay for dropdown animation to complete
  - Enhanced selectors targeting `div[@role='button']` elements within dropdown (LinkedIn's actual structure)
  - Multi-layered selector strategy with aria-label priority:
    - **Priority 1**: Aria-label matching (most specific) - `@aria-label` containing "Invite" and "connect"
    - **Priority 2**: Exact text match - `normalize-space(text())='Connect'` with XPath normalization
    - **Priority 3**: Generic role-based with manual validation - `@role='button'` elements validated individually
  - **CRITICAL: Strict validation for each dropdown item**:
    - Text must be EXACTLY "connect" (lowercase, normalized)
    - OR aria-label must contain "invite" + "connect" + "to connect"
    - Rejects dangerous keywords: 'remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect'
    - Prevents accidental clicks on "Remove connection", "Withdraw invitation", etc.
  - Detailed logging shows validation results for each candidate button
  - Handles both button and div-based dropdown items
- **Enhanced connection status detection (Feb 2026)**: Improved reliability for detecting already-connected profiles
  - Scoped search within profile header container only (prevents false positives from other page sections)
  - Uses multiple fallback selectors to locate profile header (`pv-top-card`, `pvs-sticky-header-profile-actions`, `artdeco-card`, `main//section[1]`)
  - **NEW: "Remove connection" button detection** - Now checks for "Remove connection" button as primary indicator of already-connected status
    - Searches for button text or aria-label containing "Remove connection"
    - Returns `already_connected_success` status when found (treated as successful operation)
    - Updates database with note indicating already connected
  - **Enhanced Message button detection** - Improved XPath selector using `normalize-space(text())='Message'` for exact matching
    - Checks both aria-label and exact text match for Message button
    - Returns `already_connected_success` status when found (treated as successful operation)
    - Updates database with note indicating already connected
  - **Multi-strategy Pending status detection** - Detects connection requests already sent using multiple approaches
    - **Strategy 1**: Searches for Pending button in profile header
    - **Strategy 2**: Searches for Pending text anywhere in header
    - **Strategy 3**: Checks for "Send profile in a message" option (indicates connected/pending)
    - Returns `pending_success` or `already_connected_success` status when found
  - **Pending status now treated as success** - When a connection request is already pending, the system treats it as a successful operation and updates the database with the note. This prevents duplicate tracking and ensures the lead's status is properly recorded even if the request was sent in a previous session.
  - Returns early with appropriate status (`already_connected_success` or `pending_success`) to prevent duplicate requests
  - Graceful error handling - continues if status check fails (with warning logged)
  - **Detailed logging**: Each detection strategy logs its progress for easier debugging
- **Scoped Connect button detection**: `find_connect_button()` now searches only within the profile header container to prevent false positives
  - Locates profile header using multiple fallback selectors (`pv-top-card`, `artdeco-card`, `main//section[1]`)
  - All button searches are scoped to header container using relative XPath (`.//` prefix)
  - Prevents clicking Connect buttons from other page sections (e.g., "People Also Viewed", activity feed)
  - Improved reliability by filtering out non-header Connect buttons
- **Smart Connect button detection with More dropdown fallback**: Intelligently searches for Connect button in multiple locations
  - First attempts direct Connect button with 3 optimized selectors (scoped to header)
  - If not found, automatically clicks More button and searches inside dropdown menu
  - Handles profiles where Connect is hidden in More actions menu
  - Filters for visible and enabled buttons only to avoid false positives
- Enhanced Connect button detection with improved error handling and try-except blocks
- Improved page load handling with explicit wait for main content (20 seconds timeout)
- Auto-scroll to top before button detection to ensure visibility
- Debug artifacts: Screenshots + HTML page source saved when Connect button not found
- Detailed progress logging with selector preview and error messages
- Production-ready: Worker now supports both dry-run testing and live connection requests based on job payload
- Supabase integration: Outreach worker now connects to Supabase for future tracking and analytics capabilities

**Production Mode:**
The outreach worker is now production-ready. Control the behavior using the `dry_run` flag in each job:
- `dry_run: true` - Test mode: Types message but doesn't send (for verification)
- `dry_run: false` - Production mode: Sends actual connection requests

**Supabase Integration:**
The outreach worker now connects to Supabase on startup:
- Automatically initializes Supabase connection using credentials from `.env`
- Gracefully handles connection failures - continues without Supabase if unavailable
- Logs connection status on startup for debugging
- Stores outreach results with detailed status tracking:
  - `sent` - Connection request successfully sent (production mode)
  - `dry_run_success` - Message typed but not sent (test mode) → saved as `test_run`
  - `already_connected_success` - Profile already connected (Message or Remove connection button found) → **NEW: Treated as success and database is updated with the note**
  - `pending_success` - Connection request already pending from previous session → **Treated as success and database is updated with the note**
  - `failed` - Request failed (not saved to database)
- Saves complete job metadata including message template, job ID, timestamp, and result details
- Updates `leads_list` table with appropriate `connection_status` based on outcome
- **Already connected handling**: When a profile is already connected (detected via "Message" or "Remove connection" button), the system now treats it as a successful operation with status `already_connected_success`. This ensures the database is updated with the outreach note even if the connection already exists, preventing data loss and maintaining accurate tracking.
- **Pending status handling**: When a profile has a pending connection request, the system treats it as a successful operation with status `pending_success`. This ensures the database is updated with the outreach note even if the connection was initiated in a previous session, preventing data loss and maintaining accurate tracking.

**Rate Limiting & Safety Features:**
- **Rate limiting**: 90-second delay between jobs per worker
  - With 3 workers in parallel: ~40 requests/hour per worker, ~120 requests/hour total
  - Configurable via `MAX_WORKERS` environment variable (default: 3)
  - Each worker maintains independent rate limiting
  - ⚠️ **WARNING**: Higher worker counts increase throughput but may trigger LinkedIn rate limits
  - Monitor for account restrictions and adjust worker count or delay if needed
  - For safer operation, use 1-2 workers with 90-second delays (~40-80 requests/hour)
- Screenshot capture for every attempt (success or failure)
- Detailed logging for debugging and audit trails with worker identification (`[Worker N]`)
- Graceful error handling with no automatic retries to prevent spam
- Smart status tracking prevents duplicate connection attempts
- Multi-threaded architecture for parallel processing via RabbitMQ queue distribution

## Notes

- First 10 profiles are usually accurate
- Browser restart prevents memory leak after that
- Mobile mode = simpler HTML, no "See all" buttons
- Desktop mode = full features, more data

## Database Schema

### Supabase Table: `leads_list`

The crawler stores scraped profiles in the `leads_list` table with the following schema:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key (auto-generated) |
| `profile_url` | TEXT | LinkedIn profile URL (unique) |
| `name` | TEXT | Lead's name extracted from profile |
| `profile_data` | JSONB | Complete scraped profile data as JSON |
| `connection_status` | TEXT | Status: `scraped`, `connection_sent`, `message_sent`, `connected` |
| `date` | DATE | Date when profile was scraped |
| `template_id` | UUID | Optional: Link to requirement template for filtering |
| `score` | NUMERIC | Optional: Scoring result (populated by scoring service) |
| `scored_at` | TIMESTAMP | Optional: When the profile was scored |

### Database Migration

If you're setting up a new Supabase instance or the `profile_data` column doesn't exist:

1. Open Supabase SQL Editor
2. Run the migration script:
   ```bash
   backend/crawler/add_profile_data_column.sql
   ```

The migration script:
- Checks if `profile_data` column exists before adding it
- Creates the column as JSONB type with default empty object
- Verifies the column was added successfully
- Safe to run multiple times (idempotent)

**Note:** The `profile_data` column stores the complete JSON output from the crawler, including all sections like experiences, education, skills, projects, etc.

## Recent Updates

### February 25, 2026 - Multi-Worker Architecture for Outreach System

**Change Summary:**
Refactored the outreach worker from a single-threaded consumer to a multi-threaded architecture supporting parallel job processing with configurable worker count.

**Technical Details:**
- **New `main()` function**: Entry point that spawns multiple worker threads
- **Refactored `worker()` to `worker_thread(worker_id, outreach_queue)`**: Each worker runs in its own thread with unique ID
- **Configurable worker count**: Set via `MAX_WORKERS` environment variable (default: 3)
- **Thread-safe operation**: Each worker maintains its own:
  - RabbitMQ connection and channel
  - Supabase connection
  - Browser session (created per job)
  - Rate limiting timer (90 seconds between jobs)
- **Worker identification**: All logs prefixed with `[Worker N]` for easy tracking
- **Graceful shutdown**: `Ctrl+C` stops all workers after they finish current tasks
- **Daemon threads**: Workers run as daemon threads, automatically cleaned up on main thread exit

**Architecture:**
```
main()
  ├─ Spawns Worker Thread 1 → RabbitMQ Connection → Browser Session
  ├─ Spawns Worker Thread 2 → RabbitMQ Connection → Browser Session
  └─ Spawns Worker Thread 3 → RabbitMQ Connection → Browser Session
       ↓
  RabbitMQ Queue (round-robin distribution)
       ↓
  Each worker processes jobs independently with 90s delays
```

**Impact:**
- **Increased throughput**: 3 workers = ~120 requests/hour (vs. ~40 with single worker)
- **Better resource utilization**: Parallel processing while one worker waits for rate limiting
- **Scalability**: Easy to adjust worker count based on needs and LinkedIn rate limits
- **Improved monitoring**: Worker-specific logs make debugging easier
- **Production-ready**: Handles errors gracefully per worker without affecting others

**Configuration:**
```bash
# .env file
MAX_WORKERS=3  # Adjust based on throughput needs and rate limit tolerance
```

**Throughput Examples:**
- 1 worker: ~40 requests/hour (conservative, safest)
- 2 workers: ~80 requests/hour (moderate)
- 3 workers: ~120 requests/hour (default, balanced)
- 5 workers: ~200 requests/hour (aggressive, higher rate limit risk)

**Code Changes:**
- Renamed `worker()` → `worker_thread(worker_id, outreach_queue)`
- Added `main()` function to spawn and manage worker threads
- Updated all print statements to include `[Worker {worker_id}]` prefix
- Added worker count configuration and throughput calculation
- Implemented graceful shutdown handling for all threads

**Why This Matters:**
- **Scalability**: Can handle higher outreach volumes without code changes
- **Flexibility**: Adjust worker count based on LinkedIn account health and rate limits
- **Reliability**: Worker failures don't affect other workers
- **Monitoring**: Easy to track which worker processed which job
- **Production-ready**: Designed for deployment on Railway with configurable replicas

**Deployment Note:**
When deploying to Railway, the `numReplicas` setting in `railway.json` creates multiple service instances, each running `MAX_WORKERS` threads. For example:
- `numReplicas: 3` + `MAX_WORKERS: 3` = 9 total workers across 3 service instances
- Adjust both settings carefully to avoid excessive rate limiting

---

### February 25, 2026 - Removed Strategy 4 (Message Button Detection)

**Change Summary:**
Permanently removed Strategy 4 (Message button detection) from the connection status detection system after testing phase confirmed it was not necessary for accurate status tracking.

**Technical Details:**
- **Removed code**: Deleted 18 lines of code that checked for "Message" button in profile header
- **Simplified detection flow**: System now uses only 3 strategies for connection status detection:
  - **Strategy 1**: Global Pending button detection via `//button[.//span[normalize-space()='Pending']]`
  - **Strategy 2**: Aria-label detection (case-insensitive) for pending status
  - **Strategy 3**: "Remove connection" button detection for already-connected profiles
- **Testing results**: Testing phase showed Strategy 4 was redundant with other detection methods
- **Cleaner codebase**: Removed commented-out code that was temporarily disabled for testing

**Impact:**
- **Reduced complexity**: Fewer detection strategies to maintain and debug
- **Improved performance**: One less check to perform on each profile
- **Maintained reliability**: Other strategies (1, 2, 3, and dropdown detection in `find_connect_button()`) provide complete coverage
- **Cleaner logs**: Fewer status check messages in production logs

**Why This Was Removed:**
- Strategy 4 was checking for "Message" button as an indicator of already-connected profiles
- Testing revealed this check was redundant because:
  - Strategy 3 ("Remove connection" detection) already catches connected profiles reliably
  - Dropdown menu detection in `find_connect_button()` also checks for "Remove connection"
  - Message button detection was causing false positives in some edge cases
- The scoped search (limited to profile header) was added to prevent false positives from ads, but the strategy itself proved unnecessary

**Remaining Detection Strategies:**
```python
# Strategy 1: Global Pending button detection
pending_buttons = driver.find_elements(By.XPATH, "//button[.//span[normalize-space()='Pending']]")

# Strategy 2: Aria-label detection for pending
pending_aria = driver.find_elements(By.XPATH, "//button[contains(translate(@aria-label, 'PENDING', 'pending'), 'pending')]")

# Strategy 3: "Remove connection" detection
remove_buttons = driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'REMOVE', 'remove'), 'remove') and contains(translate(text(), 'CONNECTION', 'connection'), 'connection')]")

# Strategy 5 (in find_connect_button()): Dropdown "Remove connection" detection
# Integrated into dropdown menu search loop
```

**Code Removed:**
- 18 lines of commented-out code for Message button detection
- Scoped XPath selector targeting `pvs-sticky-header-profile-actions` and `pv-top-card-v2-ctas`
- Validation logic for Message button display status
- Status update and return logic for `already_connected_success`

This cleanup is part of ongoing efforts to maintain a lean, efficient, and reliable outreach automation system based on real-world testing results.

---

### February 25, 2026 - Two-Strategy Connect Button Detection with Global Search Priority

**Change Summary:**
Implemented a two-strategy approach for Connect button detection, prioritizing a global search with specific class targeting before falling back to the header-scoped search and dropdown menu logic.

**Technical Details:**
- **Strategy 1 - Global Search (NEW - Primary)**: Searches entire page for Connect button with specific class selector
  - XPath: `//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect') and contains(@class, 'pvs-sticky-header-profile-actions__action')]`
  - Targets LinkedIn's profile action buttons specifically using the `pvs-sticky-header-profile-actions__action` class
  - Searches globally but filters by class to avoid false positives from other page sections
  - Validates button is displayed and enabled before selection
  - Logs aria-label preview (first 60 characters) for debugging
- **Strategy 2 - Header + Dropdown (Fallback)**: Uses existing `find_connect_button()` function
  - Only executes if Strategy 1 finds no buttons
  - Includes header-scoped search and More dropdown menu logic
  - Handles "Remove connection" detection for already-connected profiles
  - Returns `"ALREADY_CONNECTED"` marker when appropriate

**Impact:**
- **Improved reliability**: Global search with class filtering catches Connect buttons that might be missed by header-scoped search
- **Faster detection**: Primary strategy finds button immediately without needing to locate header container first
- **Maintains safety**: Class-based filtering prevents false positives from ads, recommendations, or other page sections
- **Graceful fallback**: If global search fails, system automatically tries header + dropdown approach
- **Better logging**: Clear strategy numbering shows which detection method succeeded

**Detection Flow:**
```
1. Try Strategy 1: Global search with class filter
   ├─ Found? → Use button
   └─ Not found? → Continue to Strategy 2

2. Try Strategy 2: Header + dropdown search
   ├─ Found in header? → Use button
   ├─ Found in dropdown? → Use button
   ├─ "Remove connection" detected? → Return ALREADY_CONNECTED
   └─ Not found? → Report failure
```

**Why This Matters:**
- LinkedIn's profile action buttons have consistent class names (`pvs-sticky-header-profile-actions__action`) that are more stable than DOM structure
- Global search eliminates dependency on finding the correct header container first
- Class-based filtering provides safety without limiting search scope
- Two-strategy approach maximizes success rate while maintaining code organization

**Code Change:**
```python
# Before (single strategy):
connect_button = find_connect_button(driver, wait)

# After (two strategies with priority):
# Strategy 1: Global search with class filter
global_connect_buttons = driver.find_elements(By.XPATH, 
    "//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect') and contains(@class, 'pvs-sticky-header-profile-actions__action')]")

if global_connect_buttons:
    for btn in global_connect_buttons:
        if btn.is_displayed() and btn.is_enabled():
            connect_button = btn
            break

# Strategy 2: Fallback to header + dropdown
if not global_connect_buttons:
    connect_button = find_connect_button(driver, wait)
```

This enhancement significantly improves Connect button detection reliability while maintaining all existing safety features and fallback mechanisms.

---

### February 25, 2026 - Enhanced Direct Connect Button Validation with Aria-Label Support

**Change Summary:**
Improved direct Connect button detection to support LinkedIn's aria-label patterns in addition to exact text matching, increasing reliability across different LinkedIn UI variations.

**Technical Details:**
- **Dual validation strategy**: Button is now validated using TWO criteria (either can pass):
  1. **Exact text match**: Button text must be exactly "connect" (case-insensitive, normalized)
  2. **Aria-label pattern match**: Aria-label must contain "invite" AND "to connect" (LinkedIn's standard pattern)
- **Improved logging**: Updated rejection messages to indicate both validation paths were checked
- **Maintains safety**: Still rejects dangerous keywords ('remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect')
- **Consistent with dropdown logic**: Direct button validation now matches the same dual-validation approach used in dropdown menu detection

**Impact:**
- **Better reliability**: Handles LinkedIn UI variations where Connect button uses aria-label instead of visible text
- **Fewer false negatives**: Catches valid Connect buttons that might have been missed with text-only validation
- **Maintains safety**: Still prevents accidental clicks on dangerous buttons like "Remove connection"
- **Consistent behavior**: Direct and dropdown Connect button detection now use the same validation logic

**Code Change:**
```python
# Before (text-only validation):
if btn_text == 'connect':
    print("  ✓ Found valid direct Connect button")
    return btn
else:
    print(f"    ✗ REJECTED: text '{btn_text}' is not exactly 'connect'")

# After (dual validation):
is_valid_text = btn_text == 'connect'
is_valid_label = 'invite' in btn_label and 'to connect' in btn_label

if is_valid_text or is_valid_label:
    print("  ✓ Found valid direct Connect button")
    return btn
else:
    print(f"    ✗ REJECTED: text '{btn_text}' not exactly 'connect' and label not valid")
```

**Why This Matters:**
LinkedIn's UI can render Connect buttons in different ways:
- Some profiles show visible "Connect" text
- Others use aria-label for accessibility with text like "Invite [Name] to connect"
- This update ensures both patterns are recognized while maintaining strict safety validation

---

### February 25, 2026 - Improved "Remove Connection" Detection in Dropdown Menu

**Change Summary:**
Consolidated duplicate detection logic for "Remove connection" button in dropdown menus to improve code maintainability and reliability.

**Technical Details:**
- **Unified detection logic**: Combined two separate checks for "Remove connection" into a single conditional statement
- **Dual validation**: Now checks both element text AND aria-label in one expression using OR operator
- **Code simplification**: Reduced from two separate if-blocks to one, eliminating redundant code
- **Maintained functionality**: Detection behavior remains identical - still catches "Remove connection" in both text and aria-label
- **Cleaner logging**: Single detection message instead of two separate messages for the same condition

**Impact:**
- More maintainable code with less duplication
- Same reliable detection of already-connected profiles
- Prevents accidental clicks on "Remove connection" button in dropdown menus
- Returns `"ALREADY_CONNECTED"` marker when detected, which triggers `already_connected_success` status
- Database is properly updated with note indicating profile is already connected

**Code Change:**
```python
# Before (two separate checks):
if 'remove' in elem_text and 'connection' in elem_text:
    return "ALREADY_CONNECTED"
if 'remove' in elem_label and 'connection' in elem_label:
    return "ALREADY_CONNECTED"

# After (unified check):
if ('remove' in elem_text and 'connection' in elem_text) or ('remove' in elem_label and 'connection' in elem_label):
    return "ALREADY_CONNECTED"
```

This change is part of ongoing improvements to the outreach automation system's reliability and code quality.

---

### February 25, 2026 - Enhanced Direct Connect Button Detection with Aria-Label Priority

**Change Summary:**
Added aria-label selector as the primary detection method for direct Connect buttons, improving reliability by leveraging LinkedIn's accessibility attributes before falling back to text-based matching.

**Technical Details:**
- **Prioritized aria-label detection**: New selector added as first priority: `.//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]`
- **Selector ordering**: Aria-label check now runs before text-based selectors
- **Maintains fallback chain**: Text-based selectors remain as fallback options if aria-label detection fails
- **Consistent validation**: All detected buttons still undergo strict validation (exact text match OR valid aria-label pattern)
- **Improved comments**: Updated inline documentation to clarify selector priority and purpose

**Impact:**
- **Higher success rate**: Aria-label attributes are more stable than visible text across LinkedIn UI updates
- **Faster detection**: Primary selector now matches LinkedIn's most reliable accessibility pattern first
- **Better accessibility compliance**: Leverages LinkedIn's ARIA attributes designed for screen readers
- **Maintains safety**: All buttons still validated against dangerous keywords before clicking

**Selector Priority Order:**
1. **Aria-label (NEW - Primary)**: `contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')`
2. **Exact text match (Fallback)**: `normalize-space(text())='Connect'`
3. **Span text match (Fallback)**: `.//span[normalize-space(text())='Connect']`

**Why This Matters:**
- LinkedIn's accessibility attributes (aria-label) are less likely to change than visible UI text
- Aria-labels provide more context (e.g., "Invite John Doe to connect") making validation more reliable
- Prioritizing aria-label detection aligns with web accessibility best practices
- Reduces false negatives when LinkedIn updates visible button text styling

**Code Change:**
```python
# Before (text-first approach):
direct_selectors = [
    ".//button[normalize-space(text())='Connect']",
    ".//button[.//span[normalize-space(text())='Connect']]",
]

# After (aria-label-first approach):
direct_selectors = [
    # By aria-label (most reliable for LinkedIn)
    ".//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]",
    # By text (fallback)
    ".//button[normalize-space(text())='Connect']",
    ".//button[.//span[normalize-space(text())='Connect']]",
]
```

This enhancement is part of the continuous improvement effort to make the outreach automation more robust against LinkedIn UI changes while maintaining strict safety validation.

---

### February 25, 2026 - Profile Area Scoping for Direct Connect Button Detection

**Change Summary:**
Enhanced direct Connect button detection to search only within the profile header area, preventing false positives from other page sections like recommendations, ads, or activity feeds.

**Technical Details:**
- **Profile area selectors**: Defined three specific profile header area selectors (most specific to least specific):
  1. `//main//section[contains(@class, 'pv-top-card')]` - Main profile card
  2. `//div[contains(@class, 'ph5')]//section` - Profile actions section
  3. `//main//div[contains(@class, 'pv-top-card-v2-ctas')]` - Profile CTA buttons
- **Scoped search strategy**: Both aria-label and text-based Connect button searches now limited to profile area only
- **Fallback mechanism**: Tries each profile area selector in order, stops at first area that contains buttons
- **Improved logging**: Updated messages to indicate "profile area" or "profile header" for clarity
- **Maintains safety**: All existing validation (dangerous keyword filtering, exact text matching) remains intact

**Impact:**
- **Eliminates false positives**: No longer detects Connect buttons from "People Also Viewed", LinkedIn ads, or activity feed items
- **Higher accuracy**: Only clicks Connect buttons that belong to the actual profile being viewed
- **Better reliability**: Profile area selectors are more stable than global page searches
- **Clearer debugging**: Logs now explicitly state when buttons are found "in profile area"

**Detection Flow:**
```
Step 1: Looking for Connect button in profile header
  ├─ Try profile area selector 1: pv-top-card
  │   ├─ Search for aria-label "Invite...to connect"
  │   └─ Search for text "Connect"
  ├─ Try profile area selector 2: ph5 section
  │   ├─ Search for aria-label "Invite...to connect"
  │   └─ Search for text "Connect"
  └─ Try profile area selector 3: pv-top-card-v2-ctas
      ├─ Search for aria-label "Invite...to connect"
      └─ Search for text "Connect"
```

**Why This Matters:**
- LinkedIn pages contain multiple Connect buttons (recommendations, ads, etc.)
- Global searches could accidentally click wrong Connect buttons
- Profile area scoping ensures we only interact with the target profile's buttons
- Reduces risk of sending connection requests to wrong people

**Code Change:**
```python
# Before (global search):
connect_buttons = driver.find_elements(By.XPATH, 
    "//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")

# After (profile area scoped):
profile_area_selectors = [
    "//main//section[contains(@class, 'pv-top-card')]",
    "//div[contains(@class, 'ph5')]//section",
    "//main//div[contains(@class, 'pv-top-card-v2-ctas')]",
]

for area_selector in profile_area_selectors:
    connect_buttons = driver.find_elements(By.XPATH, 
        f"{area_selector}//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")
    if connect_buttons:
        break  # Found buttons in this area, stop searching
```

**Safety Features Maintained:**
- Dangerous keyword filtering still active ('remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect')
- Exact text validation still required (text must be exactly "connect")
- Aria-label pattern validation still enforced ("invite" + "to connect")
- Button must be displayed and enabled before selection

This enhancement significantly improves the precision of Connect button detection while maintaining all existing safety mechanisms and validation logic.

---

### February 25, 2026 - Removed Redundant Primary Button Style Check (Strategy 3)

**Change Summary:**
Removed Strategy 3 (primary button style check) from the direct Connect button detection logic as it was redundant with the existing profile area scoping and aria-label detection strategies.

**Technical Details:**
- **Removed code**: Deleted 19 lines of code that checked for Connect buttons with `artdeco-button--primary` class
- **Simplified detection flow**: Direct Connect button detection now uses only 2 strategies:
  1. **Aria-label detection** (primary): Searches for buttons with aria-label containing "Invite" and "to connect"
  2. **Text-based detection** (fallback): Searches for buttons with exact text "Connect"
- **Profile area scoping maintained**: Both strategies still search only within profile header areas (pv-top-card, ph5, pv-top-card-v2-ctas)
- **Y-position validation removed**: No longer needed since profile area scoping already prevents false positives

---

### March 2, 2026 - Search Input Data Format Standardization

**Change Summary:**
Updated `data/search_input.json` to use standardized field names consistent with the rest of the crawler system, replacing `linkedin_url` with `profile_url` and adding `connection_status` field.

**Technical Details:**
- **Field name change**: Renamed `linkedin_url` → `profile_url` for consistency across all crawler components
- **New field added**: Added `connection_status` field with value `"scraped"` to indicate profile scraping status
- **Template ID updated**: Changed from `8191cb53-725e-46f5-a54a-79affc378811` to `9a0ac72d-0b94-4c4a-ae77-6e590213bbf1`
- **Data reduction**: Reduced from 375 entries to 230 entries (removed entries without profile URLs)
- **Consistent schema**: Now matches the schema used by `leads_list` table and other crawler outputs

**New Data Format:**
```json
[
  {
    "template_id": "9a0ac72d-0b94-4c4a-ae77-6e590213bbf1",
    "name": "Ronald T.",
    "profile_url": "https://www.linkedin.com/in/ronald-tansil",
    "connection_status": "scraped"
  }
]
```

**Old Data Format:**
```json
[
  {
    "template_id": "8191cb53-725e-46f5-a54a-79affc378811",
    "name": "Alesandro Michael Ferdinand",
    "linkedin_url": "https://www.linkedin.com/in/alesandro-michael-ferdinand"
  }
]
```

**Impact:**
- **Improved consistency**: All crawler components now use `profile_url` field name
- **Better integration**: Data format matches Supabase `leads_list` table schema
- **Status tracking**: `connection_status` field enables better workflow tracking
- **Reduced confusion**: Eliminates field name discrepancies between different parts of the system

**Affected Components:**
- `crawler_consumer.py` - Reads `profile_url` from input files
- `crawler_search.py` - Outputs `profile_url` in search results
- `scheduler_daemon.py` - Expects `profile_url` in JSON files
- Supabase `leads_list` table - Uses `profile_url` as primary identifier

**Migration Note:**
If you have existing JSON files using `linkedin_url`, they should be updated to use `profile_url` for compatibility with the latest crawler version. The field name change is backward compatible in most cases, but using the standardized name is recommended for consistency.

**Why This Matters:**
- Consistent field naming reduces bugs and confusion when working with profile data
- Matches the naming convention used throughout the codebase (Supabase schema, API responses, etc.)
- Makes it easier to integrate with other services and maintain the codebase
- Aligns with the documented schema in README and code comments

**Why This Was Removed:**
- **Redundant filtering**: Profile area scoping already ensures we only find buttons in the correct location
- **Class-based filtering unnecessary**: The `artdeco-button--primary` class check was an additional filter on top of profile area scoping, providing no additional value
- **Y-position check obsolete**: Checking if button is in top 1000px of page is redundant when we're already searching within specific profile header containers
- **Simpler is better**: Fewer detection strategies means easier maintenance and debugging

**Impact:**
- **Reduced complexity**: One less detection strategy to maintain
- **Improved performance**: Fewer XPath queries and validation checks per profile
- **Maintained reliability**: Profile area scoping and aria-label detection provide complete coverage
- **Cleaner code**: Removed unnecessary filtering that duplicated existing safeguards

**Detection Flow (After Removal):**
```
Step 1: Looking for Connect button in profile header
  For each profile area (pv-top-card, ph5, pv-top-card-v2-ctas):
    ├─ Strategy 1: Search for aria-label "Invite...to connect"
    │   ├─ Validate button is displayed and enabled
    │   ├─ Check for dangerous keywords
    │   └─ Validate text is "connect" OR aria-label is valid
    └─ Strategy 2: Search for text "Connect"
        ├─ Validate button is displayed and enabled
        ├─ Check for dangerous keywords
        └─ Validate text is "connect" OR aria-label is valid
```

**Code Removed:**
```python
# Strategy 3: Search by aria-label but filter by button style (primary = profile, muted/secondary = recommendations)
try:
    connect_buttons = driver.find_elements(By.XPATH, 
        "//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect') and contains(@class, 'artdeco-button--primary')]")
    
    for btn in connect_buttons:
        try:
            if btn.is_displayed() and btn.is_enabled():
                # Check Y position as last resort (should be in top 1000px)
                location = btn.location
                if location['y'] < 1000:
                    btn_label = btn.get_attribute('aria-label') or ''
                    print(f"  ✓ Found Connect button (primary style): {btn_label[:60]}")
                    return btn
        except:
            continue
except Exception as e:
    print(f"  ⚠️  Error searching Connect by primary style: {e}")
```

**Remaining Safeguards:**
- Profile area scoping (searches only within pv-top-card, ph5, pv-top-card-v2-ctas containers)
- Aria-label pattern validation ("invite" + "to connect")
- Exact text matching (must be exactly "connect")
- Dangerous keyword filtering ('remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect')
- Display and enabled state validation

This cleanup is part of ongoing efforts to maintain a lean, efficient, and reliable outreach automation system by removing redundant code that doesn't add value.

---

### February 25, 2026 - Architectural Refactor: Unified Button Detection and Status Checking

**Change Summary:**
Moved connection status checking logic from `send_connection_request()` into `find_connect_button()`, creating a unified function that handles both button detection and status validation in a single pass.

**Technical Details:**
- **Removed duplicate code**: Eliminated 73 lines of connection status checking from `send_connection_request()`
- **Unified detection flow**: `find_connect_button()` now performs all detection and validation:
  1. **Step 1-3**: Search for Connect, Pending, and "Remove connection" buttons in header
  2. **Step 4**: Open More dropdown if no buttons found in header
  3. **Step 5-7**: Search dropdown for "Remove connection", Pending, and Connect buttons
- **Cleaner architecture**: Single function responsible for all button-related logic
- **Maintained functionality**: All detection strategies remain identical, just consolidated into one location
- **Improved maintainability**: Changes to detection logic now only need to be made in one place

**What Was Moved:**
The following connection status checks were moved from `send_connection_request()` to `find_connect_button()`:
- **Strategy 1**: Global Pending button detection via `//button[.//span[normalize-space()='Pending']]`
- **Strategy 2**: Aria-label detection (case-insensitive) for pending status
- **Strategy 3**: "Remove connection" button detection for already-connected profiles

**Detection Flow (Before):**
```
send_connection_request():
  1. Navigate to profile
  2. Check for Pending (Strategy 1)
  3. Check for Pending by aria-label (Strategy 2)
  4. Check for "Remove connection" (Strategy 3)
  5. Call find_connect_button() to find Connect button
  6. Click Connect and send message

find_connect_button():
  1. Search header for Connect
  2. Open More dropdown if not found
  3. Search dropdown for Connect
```

**Detection Flow (After - Unified):**
```
send_connection_request():
  1. Navigate to profile
  2. Call find_connect_button() (handles all detection)
  3. Handle special status returns (PENDING, ALREADY_CONNECTED)
  4. Click Connect and send message

find_connect_button():
  1. Search header for Connect
  2. Search header for Pending → return "PENDING"
  3. Search header for "Remove connection" → return "ALREADY_CONNECTED"
  4. Open More dropdown if nothing found
  5. Search dropdown for "Remove connection" → return "ALREADY_CONNECTED"
  6. Search dropdown for Pending → return "PENDING"
  7. Search dropdown for Connect
```

**Impact:**
- **Reduced code duplication**: Connection status checking logic exists in only one place
- **Improved maintainability**: Easier to update detection strategies - change once, applies everywhere
- **Better code organization**: Single function responsible for all button-related decisions
- **Same reliability**: All detection strategies remain unchanged, just consolidated

---

### February 25, 2026 - Simplified Connect Button Detection with Three Focused Strategies

**Change Summary:**
Refactored `find_connect_button()` to use three highly-targeted detection strategies that prioritize LinkedIn's most reliable UI patterns, eliminating profile area scoping complexity while maintaining accuracy.

**Technical Details:**
- **Strategy 1 - Sticky Header Button (Most Reliable)**: Targets LinkedIn's sticky profile header button
  - XPath: `//button[contains(@class, 'pvs-sticky-header-profile-actions__action') and contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]`
  - Uses LinkedIn's specific class name for profile action buttons
  - Validates button is displayed and enabled
  - Logs aria-label preview (first 60 characters) for debugging
  
- **Strategy 2 - ph5 Container Button**: Searches main profile area with style validation
  - XPath: `//div[contains(@class, 'ph5')]//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]`
  - Extra validation: Checks for primary button styling (`artdeco-button--primary` or `pvs-sticky-header`)
  - Filters out muted/secondary buttons from recommendations
  - Ensures button is in main profile area, not ads or suggestions
  
- **Strategy 3 - Primary Style Button with Position Check**: Global search with strict filtering
  - XPath: `//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect') and contains(@class, 'artdeco-button--primary')]`
  - Validates button Y-position is in top 1000px of page
  - Last resort check to catch edge cases
  - Prevents clicking buttons far down the page

**What Was Removed:**
- Profile area selector definitions (`pv-top-card`, `ph5//section`, `pv-top-card-v2-ctas`)
- Nested loops iterating through profile areas
- Text-based Connect button detection (now relies solely on aria-label)
- Complex fallback chain with multiple selector types

**Impact:**
- **Simpler code**: Reduced from ~60 lines to ~40 lines for direct button detection
- **More reliable**: Targets LinkedIn's most stable UI patterns (class names + aria-labels)
- **Better performance**: Three focused checks instead of nested loops through multiple areas
- **Easier maintenance**: Clear strategy numbering and purpose for each detection method
- **Maintained safety**: Still validates button display status, styling, and position

**Detection Flow:**
```
Step 1: Try sticky header button (pvs-sticky-header-profile-actions__action)
  ├─ Found and valid? → Return button
  └─ Not found? → Continue to Step 2

Step 2: Try ph5 container with style validation
  ├─ Found with primary styling? → Return button
  └─ Not found? → Continue to Step 3

Step 3: Try primary style button with position check
  ├─ Found in top 1000px? → Return button
  └─ Not found? → Report "Connect button not found in profile header"

Step 4: Check for Pending button (if no Connect found)
Step 5: Check for "Remove connection" button (if no Connect found)
Step 6: Open More dropdown and search inside (if nothing found in header)
```

**Why This Matters:**
- LinkedIn's UI uses consistent class names (`pvs-sticky-header-profile-actions__action`, `artdeco-button--primary`) that are more stable than DOM structure
- Aria-label patterns (`Invite...to connect`) are standardized across LinkedIn's accessibility implementation
- Eliminating profile area scoping reduces complexity without sacrificing accuracy
- Three focused strategies cover all legitimate Connect button locations while filtering out false positives

**Code Change:**
```python
# Before (profile area scoped with multiple selectors):
profile_area_selectors = [
    "//main//section[contains(@class, 'pv-top-card')]",
    "//div[contains(@class, 'ph5')]//section",
    "//main//div[contains(@class, 'pv-top-card-v2-ctas')]",
]

for area_selector in profile_area_selectors:
    # Aria-label search
    connect_buttons = driver.find_elements(By.XPATH, 
        f"{area_selector}//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")
    # Text search
    connect_buttons = driver.find_elements(By.XPATH, 
        f"{area_selector}//button[.//span[normalize-space()='Connect']]")
    # ... validation logic

# After (three focused strategies):
# Strategy 1: Sticky header button
connect_buttons = driver.find_elements(By.XPATH, 
    "//button[contains(@class, 'pvs-sticky-header-profile-actions__action') and contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")

# Strategy 2: ph5 container with style validation
connect_buttons = driver.find_elements(By.XPATH, 
    "//div[contains(@class, 'ph5')]//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")
if 'artdeco-button--primary' in btn_class or 'pvs-sticky-header' in btn_class:
    return btn

# Strategy 3: Primary style with position check
connect_buttons = driver.find_elements(By.XPATH, 
    "//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect') and contains(@class, 'artdeco-button--primary')]")
if location['y'] < 1000:
    return btn
```

**Benefits:**
- **Clearer intent**: Each strategy has a specific purpose and target
- **Better logging**: Strategy numbers make debugging easier
- **Reduced complexity**: No nested loops or complex selector chains
- **Maintained accuracy**: Still filters out recommendations, ads, and non-profile buttons
- **Future-proof**: Relies on LinkedIn's stable accessibility patterns

This refactor is part of ongoing efforts to simplify the codebase while maintaining high reliability for automated outreach operations.trategies preserved, just reorganized
- **Cleaner logs**: Detection steps now flow logically from 1-7 in a single function

**Return Values:**
`find_connect_button()` now returns:
- **WebElement**: Valid Connect button found (ready to click)
- **"PENDING"**: Connection request already pending (treated as success)
- **"ALREADY_CONNECTED"**: Profile already connected (treated as success)
- **None**: No valid button found (error state)

**Why This Matters:**
- **Single Responsibility Principle**: `find_connect_button()` is now the single source of truth for all button detection and status checking
- **Easier Testing**: All detection logic can be tested through one function
- **Reduced Complexity**: `send_connection_request()` is now simpler and focuses on the message sending workflow
- **Better Error Handling**: Status detection happens before any click actions, preventing unnecessary operations

**Code Removed from `send_connection_request()`:**
```python
# REMOVED: 73 lines of duplicate status checking
# - Strategy 1: Global Pending button detection
# - Strategy 2: Aria-label detection for pending
# - Strategy 3: "Remove connection" detection
# All now handled by find_connect_button()
```

**Code Enhanced in `find_connect_button()`:**
```python
# ADDED: Steps 2, 3, 5, 6 for status checking
# Step 2: Check for Pending in header
# Step 3: Check for "Remove connection" in header
# Step 5: Check for "Remove connection" in dropdown
# Step 6: Check for Pending in dropdown
# Returns special markers: "PENDING" or "ALREADY_CONNECTED"
```

This architectural improvement makes the codebase more maintainable while preserving all existing functionality and reliability. The refactor follows the DRY (Don't Repeat Yourself) principle and improves code organization without changing behavior.

---

## Railway Deployment Configuration

The crawler service is configured for deployment on Railway using the `railway.json` configuration file.

### Current Configuration

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "numReplicas": 3,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Deployment Settings

**Replicas**: 3 parallel workers
- Enables concurrent processing of outreach jobs from RabbitMQ queue
- Each worker processes jobs independently with 30-second delays between jobs
- Combined throughput: ~6 requests/minute, ~360/hour, ~8,640/day
- ⚠️ **Rate Limiting Warning**: This is an aggressive configuration that may trigger LinkedIn rate limits
- Monitor for account restrictions and adjust `numReplicas` or increase delays if needed

**Restart Policy**: ON_FAILURE with 10 max retries
- Automatically restarts workers if they crash or encounter errors
- Prevents service downtime from transient failures
- Max 10 restart attempts before giving up (prevents infinite restart loops)

### Scaling Considerations

**Increasing Replicas:**
- More replicas = higher throughput but increased risk of rate limiting
- Recommended: Start with 1-2 replicas and monitor LinkedIn account health
- If scaling beyond 3 replicas, increase delay between jobs to 60+ seconds

**Decreasing Replicas:**
- Safer for LinkedIn account health
- Lower throughput but reduced risk of rate limiting
- Recommended for conservative operation: 1 replica with 60-second delays

**Monitoring:**
- Check Railway logs for rate limit warnings or connection errors
- Monitor LinkedIn account for restrictions or verification requests
- Track success/failure rates in Supabase `leads_list` table
- Adjust `numReplicas` based on observed behavior

### Deployment Commands

```bash
# Deploy to Railway (from backend/crawler directory)
railway up

# View logs
railway logs

# Check service status
railway status
```

**Note:** Ensure all required environment variables are set in Railway dashboard before deployment (see Configuration section above for required variables).


---

### February 25, 2026 - Rate Limiting Adjustment: 60-Second Delay Between Jobs

**Change Summary:**
Reduced the rate limiting delay from 90 seconds to 60 seconds per worker to increase outreach throughput while maintaining reasonable LinkedIn rate limit compliance.

**Technical Details:**
- **Previous delay**: 90 seconds between jobs per worker
- **New delay**: 60 seconds between jobs per worker
- **Throughput impact**:
  - Single worker: ~40 requests/hour → ~60 requests/hour (+50% increase)
  - 3 workers (default): ~120 requests/hour → ~180 requests/hour (+50% increase)
  - 5 workers: ~200 requests/hour → ~300 requests/hour (+50% increase)
- **Code change**: Updated `delay` variable in `worker_thread()` function from 90 to 60
- **Configuration**: Delay is hardcoded in `crawler_outreach.py` line 802

**Impact:**
- **Increased throughput**: 50% more connection requests per hour across all worker configurations
- **Moderate risk level**: 60-second delays are still within reasonable LinkedIn rate limits for most accounts
- **Better efficiency**: Reduces time to complete large outreach campaigns
- **Maintained safety**: Each worker still waits between jobs to avoid triggering rate limits

**Updated Throughput Calculations:**
```
Single Worker (1 worker × 60s delay):
  - ~60 requests/hour
  - ~1,440 requests/day
  - ~43,200 requests/month

Default Configuration (3 workers × 60s delay):
  - ~180 requests/hour
  - ~4,320 requests/day
  - ~129,600 requests/month

Aggressive Configuration (5 workers × 60s delay):
  - ~300 requests/hour
  - ~7,200 requests/day
  - ~216,000 requests/month
```

**Scaling Recommendations (Updated):**
- **Conservative**: 1-2 workers with 60-second delays (~60-120 requests/hour) - Safest for new accounts
- **Moderate (Default)**: 3 workers with 60-second delays (~180 requests/hour) - Balanced throughput and safety
- **Aggressive**: 5+ workers with 60-second delays (~300+ requests/hour) - ⚠️ Higher risk of rate limiting

**Monitoring Recommendations:**
- Watch for LinkedIn account restrictions or warnings
- Monitor for "Too many requests" errors in worker logs
- If rate limiting occurs, consider:
  - Reducing `MAX_WORKERS` count
  - Increasing delay back to 90 seconds or higher
  - Implementing dynamic delay adjustment based on error rates

**Rollback Instructions:**
If rate limiting becomes an issue, revert the change:
```python
# In crawler_outreach.py, line 802:
delay = 90  # Change back from 60 to 90
```

**Why This Change:**
- Testing showed 90-second delays were overly conservative for most LinkedIn accounts
- 60-second delays provide better throughput while maintaining acceptable risk levels
- Allows faster completion of outreach campaigns without significantly increasing rate limit risk
- Aligns with industry best practices for LinkedIn automation (1-2 requests per minute per account)

**Note:** This change affects the hardcoded delay in the worker thread. Future enhancements could make this configurable via environment variable for easier adjustment without code changes.


## Queue Management Utilities

### Queue Purge Script

The `purge.py` script provides a quick way to clear all messages from a RabbitMQ queue. This is useful for:
- Clearing test messages during development
- Resetting queues before production deployment
- Removing stale or invalid jobs from the queue

**Usage:**

1. Edit `purge.py` to change the queue name if needed (currently set to `"outreach_queue"`):
```python
channel.queue_purge(queue="outreach_queue")  # Change to your target queue
```

2. Run the script:
```bash
python purge.py
```

**Note:** The script currently purges the `outreach_queue` by default. Modify the queue name in the `channel.queue_purge()` call to target a different queue.

**Configuration:**

The script uses hardcoded LavinMQ credentials from your `.env` file:
```python
credentials = pika.PlainCredentials(
    "fexihtwb",
    "ETd7Y9BSMTZWZnKtqGQr5ikP4o63oB0u"
)

parameters = pika.ConnectionParameters(
    host="leopard.lmq.cloudamqp.com",
    port=5671,  # SSL/TLS enabled
    virtual_host="fexihtwb",
    credentials=credentials,
    ssl_options=pika.SSLOptions(ssl_context)
)
```

**Output:**
```
PURGED: your_queue_name
```

**Common Queue Names:**
- `outreach_queue` - Automated LinkedIn connection requests
- `linkedin_profiles` - Profile URLs to scrape
- `scoring_queue` - Profiles to score against requirements

**⚠️ Warning:**
- This operation is **irreversible** - all messages in the queue will be permanently deleted
- Use with caution in production environments
- Consider backing up important jobs before purging

**When to Use:**
- **Development**: Clear test messages between development iterations
- **Debugging**: Remove problematic jobs that are causing worker errors
- **Maintenance**: Clean up queues before deploying new versions
- **Emergency**: Stop processing of incorrect or duplicate jobs

**Alternative Approach:**

For more control, use the RabbitMQ Management UI:
1. Open: https://leopard.lmq.cloudamqp.com (LavinMQ web interface)
2. Login with your credentials
3. Navigate to Queues tab
4. Select queue and click "Purge Messages"


---

### February 25, 2026 - Simplified Pending Button Detection in Profile Header

**Change Summary:**
Streamlined the Pending button detection logic in Step 2 of `find_connect_button()` by removing redundant sticky header search and consolidating to a single ph5 area search.

**Technical Details:**
- **Removed Strategy 1**: Eliminated sticky header Pending button search (`pvs-sticky-header-profile-actions__action` class selector)
- **Simplified to single strategy**: Now uses only ph5 area search for Pending button detection
- **XPath selector**: `//div[contains(@class, 'ph5')]//button[.//span[normalize-space()='Pending']]`
- **Maintained functionality**: Still detects Pending buttons reliably, just with simpler code
- **Reduced code**: Removed 13 lines of duplicate detection logic

**Impact:**
- **Cleaner code**: Single detection strategy instead of two redundant checks
- **Better maintainability**: Fewer lines to maintain and debug
- **Same reliability**: ph5 area search catches all Pending buttons in profile header
- **Improved performance**: One XPath query instead of two

**Detection Flow (Before):**
```
Step 2: Checking for Pending button in profile header
  ├─ Strategy 1: Search in sticky header (pvs-sticky-header-profile-actions__action)
  │   └─ Found? → Return "PENDING"
  └─ Strategy 2: Search in ph5 area
      └─ Found? → Return "PENDING"
```

**Detection Flow (After):**
```
Step 2: Checking for Pending button in profile header
  └─ Search in ph5 area
      └─ Found? → Return "PENDING"
```

**Why This Change:**
- The sticky header search was redundant - ph5 area search already covers the profile header
- LinkedIn's Pending button appears in the ph5 container, making the sticky header check unnecessary
- Simplifying to one strategy reduces code complexity without sacrificing reliability
- Aligns with the principle of removing redundant code identified in previous refactoring efforts

**Code Removed:**
```python
# Strategy 1: Search in sticky header
pending_buttons = driver.find_elements(By.XPATH, 
    "//button[contains(@class, 'pvs-sticky-header-profile-actions__action') and .//span[normalize-space()='Pending']]")

for btn in pending_buttons:
    try:
        if btn.is_displayed():
            print("  ✅ Found Pending button in sticky header - request already sent!")
            return "PENDING"
    except:
        continue
```

**Code Retained:**
```python
# Search in ph5 area
pending_buttons = driver.find_elements(By.XPATH, 
    "//div[contains(@class, 'ph5')]//button[.//span[normalize-space()='Pending']]")

for btn in pending_buttons:
    try:
        if btn.is_displayed():
            # Check if it's primary/secondary button (not from recommendations which are muted)
            btn_class = btn.get_attribute('class') or ''
            if 'artdeco-button--primary' in btn_class or 'artdeco-button--secondary' in btn_class:
                print("  ✅ Found Pending button in ph5 area - request already sent!")
                return "PENDING"
    except:
        continue
```

**Benefits:**
- **Reduced complexity**: One detection path instead of two
- **Easier debugging**: Fewer code paths to trace when troubleshooting
- **Maintained accuracy**: ph5 area search with button style validation provides complete coverage
- **Consistent with refactoring goals**: Continues the effort to remove redundant detection strategies

**Related Changes:**
This change is part of the ongoing simplification effort that previously removed:
- Strategy 4 (Message button detection) - Feb 25, 2026
- Strategy 3 (Primary button style check for Connect) - Feb 25, 2026
- Redundant "Remove connection" checks in dropdown - Feb 25, 2026

All removals maintain the same reliability while reducing code complexity and improving maintainability.



## Authentication & Session Management

### Enhanced Cookie Session Validation (Feb 2026)

The authentication system now includes improved session validation to detect expired cookies more reliably:

**Session Verification Process:**
- After loading cookies, the system navigates to LinkedIn feed (`/feed/`) to verify the session
- Checks multiple URL patterns to confirm successful authentication:
  - `feed` - LinkedIn feed page
  - `mynetwork` - Network page
  - `/in/` - Profile pages
  - `login` or `uas/login` - Login page (indicates expired session)
- Provides clear feedback on session status with detailed logging

**Benefits:**
- **Faster failure detection**: Immediately identifies expired cookies instead of failing during scraping
- **Better error messages**: Clear indication when session has expired vs. other authentication issues
- **Graceful fallback**: Automatically triggers fresh login when cookies are invalid
- **Reduced wasted time**: Prevents starting scraping jobs with invalid sessions

**Session Validation States:**
1. **Valid Session**: Successfully navigated to feed/network/profile page
2. **Expired Session**: Redirected to login page - triggers fresh authentication
3. **Unknown State**: Not on login page but URL unclear - assumes valid (conservative approach)

**Usage:**
No configuration changes needed. The enhanced validation runs automatically when:
- Starting crawler consumer workers
- Running scheduler daemon jobs
- Executing outreach workers
- Any operation that calls `login()` function

**Troubleshooting:**
If you see "⚠ Session expired, cookies invalid":
1. Delete existing cookies: `rm data/cookie/.linkedin_cookies.json`
2. Run crawler again - it will prompt for fresh login
3. For OAuth accounts, ensure `USE_OAUTH_LOGIN=true` in `.env`
4. Complete login in browser and press ENTER when prompted



---

## LinkedIn Profile Search Crawler

### Overview

The `crawler_search.py` module provides automated LinkedIn profile search functionality. It searches for profiles by name and extracts profile URLs, making it easy to build lists of LinkedIn profiles for further processing.

### Features

- **Name-based search**: Search LinkedIn profiles by person's name
- **Automated URL extraction**: Automatically extracts the first matching profile URL
- **Batch processing**: Process JSON files containing multiple names
- **Smart validation**: Filters out invalid URLs (companies, schools, posts, etc.)
- **URL cleaning**: Removes query parameters for clean profile URLs
- **No results detection**: Identifies when searches return no results
- **Rate limiting**: Built-in delays to avoid LinkedIn rate limits
- **Session persistence**: Uses saved cookies for authentication

### Usage

#### Command Line

Process a JSON file containing names:

```bash
python crawler_search.py input.json [output.json]
```

**Examples:**
```bash
# Overwrite input file with results
python crawler_search.py data/names.json

# Save results to a different file
python crawler_search.py data/names.json data/names_with_urls.json
```

#### Input JSON Format

The input file must be a JSON array of objects with a `name` field:

```json
[
  {
    "name": "John Doe",
    "company": "Acme Corp"
  },
  {
    "name": "Jane Smith",
    "title": "Software Engineer"
  }
]
```

#### Output JSON Format

The script adds a `profile_url` field to each object:

```json
[
  {
    "name": "John Doe",
    "company": "Acme Corp",
    "profile_url": "https://www.linkedin.com/in/johndoe"
  },
  {
    "name": "Jane Smith",
    "title": "Software Engineer",
    "profile_url": "https://www.linkedin.com/in/janesmith"
  }
]
```

If a profile is not found, `profile_url` will be `null`.

**Breaking Change (Latest Update)**: The output field has been renamed from `linkedin_url` to `profile_url` for consistency with the rest of the crawler system. If you have existing code that reads this field, please update your references accordingly.

#### Python API

Use the crawler programmatically in your code:

```python
from crawler_search import LinkedInSearchCrawler

# Initialize crawler (automatically logs in)
crawler = LinkedInSearchCrawler()

# Search for a single profile
profile_url = crawler.search_profile("John Doe")
if profile_url:
    print(f"Found: {profile_url}")
else:
    print("Profile not found")

# Process a JSON file
crawler.process_json_file("data/names.json", "data/output.json")

# Close browser when done
crawler.close()
```

### How It Works

1. **Login**: Uses saved cookies from `data/cookie/.linkedin_cookies.json` for authentication
2. **Search**: Constructs LinkedIn search URL with encoded name
3. **Wait**: Waits for search results page to load (10 second timeout)
4. **Validate**: Checks if search returned results or "No results" message
5. **Extract**: Finds the first valid profile URL from search results
6. **Clean**: Removes query parameters and normalizes URL format
7. **Rate limit**: Waits 3-7 seconds between searches to avoid detection

### URL Validation

The crawler validates profile URLs to ensure they are actual LinkedIn profiles:

**Valid URLs:**
- `https://www.linkedin.com/in/username`
- `https://linkedin.com/in/username`

**Invalid URLs (filtered out):**
- Company pages: `/company/`
- School pages: `/school/`
- Posts: `/posts/`
- Feed items: `/feed/`
- Groups: `/groups/`
- Events: `/events/`

### Search Selectors

The crawler uses multiple XPath selectors to find profile links, prioritized by reliability:

1. `//a[contains(@href, '/in/') and contains(@class, 'app-aware-link')]` - Primary selector
2. `//a[contains(@href, 'linkedin.com/in/')]` - Fallback for full URLs
3. `//span[contains(@class, 'entity-result__title')]//a[contains(@href, '/in/')]` - Result title links
4. `//div[contains(@class, 'entity-result')]//a[contains(@href, '/in/')]` - Generic result links

### Error Handling

The crawler handles various error scenarios gracefully:

- **Timeout waiting for results**: Returns `None` and logs warning
- **No results found**: Detects "No results" message and returns `None`
- **Invalid JSON format**: Validates input file is a JSON array
- **Missing name field**: Skips entries without `name` field
- **Network errors**: Catches exceptions and continues processing

### Rate Limiting

To avoid LinkedIn rate limits and detection:

- **Between searches**: 3-7 second random delay
- **Page load wait**: 2-3 second delay after page loads
- **Element wait**: 1-2 second delay before extracting URLs

**Recommended usage:**
- Process small batches (10-20 names at a time)
- Run during off-peak hours
- Monitor for CAPTCHA or rate limit warnings
- Use saved cookies to avoid repeated logins

### Output Summary

After processing, the crawler displays a summary:

```
Summary:
  Total entries: 10
  Found: 8
  Not found: 2

Entries without LinkedIn URL:
  - John Unknown
  - Jane Notfound
```

### Integration with Main Crawler

The search crawler can be used as a preprocessing step before the main profile crawler:

```python
from crawler_search import LinkedInSearchCrawler
from crawler import LinkedInCrawler

# Step 1: Search for profile URLs
search_crawler = LinkedInSearchCrawler()
search_crawler.process_json_file("names.json", "profiles_with_urls.json")
search_crawler.close()

# Step 2: Scrape full profile data
profile_crawler = LinkedInCrawler()
# ... load URLs from profiles_with_urls.json and scrape
profile_crawler.close()
```

### Troubleshooting

**"No results found" for valid names:**
- Name spelling might be incorrect
- Profile might not be public
- LinkedIn search might require more specific query (add company, location, etc.)

**Timeout waiting for search results:**
- Network connection slow
- LinkedIn page structure changed
- Increase timeout in `WebDriverWait(self.driver, 10)` to higher value

**Wrong profile extracted:**
- Multiple people with same name
- Consider adding additional filters (company, location) to search query
- Manually verify extracted URLs before scraping

**Rate limiting / CAPTCHA:**
- Reduce batch size
- Increase delays between searches
- Wait before retrying
- Use different LinkedIn account

**Browser not visible during development:**
- Set `HEADLESS=false` in `.env` to force visible browser mode
- Useful for debugging and watching the crawler in action
- See "Headless Mode Configuration" section below for details

## Headless Mode Configuration

The crawler supports flexible browser visibility control through the `HEADLESS` environment variable. This allows you to force visible or headless mode regardless of the environment.

### Configuration Options

Add to your `.env` file:

```bash
# Force visible browser (for development/debugging)
HEADLESS=false

# Force headless mode (for production/background)
HEADLESS=true

# Auto-detect (omit or leave empty)
# HEADLESS=
```

### Behavior

**Priority System:**
1. **Explicit HEADLESS setting** - If set to `true`/`false`, always uses that mode
2. **Auto-detection** - If not set, detects production environment (Docker/Render) and uses headless mode automatically

**Accepted Values:**
- **Force Visible**: `false`, `0`, `no` (case-insensitive)
- **Force Headless**: `true`, `1`, `yes` (case-insensitive)
- **Auto-detect**: Empty string or omit the variable

### Use Cases

**Development/Debugging:**
```bash
HEADLESS=false
```
- Watch the crawler navigate LinkedIn in real-time
- Debug element selection issues
- Verify login flow
- Inspect page state during errors

**Production/Background:**
```bash
HEADLESS=true
```
- Run crawler on servers without display
- Reduce resource usage
- Run multiple instances in parallel
- Docker/cloud deployments

**Auto-detect (Default):**
```bash
# Omit HEADLESS variable or leave empty
```
- Automatically uses headless mode in production (Docker, Render)
- Automatically uses visible mode in local development
- Best for environments that switch between dev and prod

### Console Output

The crawler logs the selected mode on startup:

```
🔧 Running in VISIBLE mode (HEADLESS=false)
🔧 Running in HEADLESS mode (HEADLESS=true)
🔧 Running in HEADLESS mode (production detected)
🔧 Running in VISIBLE mode (development)
```

### Technical Details

- Uses Chrome's new headless mode (`--headless=new`) for better stability
- Headless mode includes `--disable-software-rasterizer` for performance
- All anti-detection features work in both modes
- Cookie persistence works identically in both modes

### Recent Updates

**February 27, 2026 - Initial Implementation**
- Added `LinkedInSearchCrawler` class for name-based profile search
- Implemented automated URL extraction from search results
- Added batch processing for JSON files with multiple names
- Included smart URL validation and cleaning
- Built-in rate limiting and error handling
- Session persistence using saved cookies


## RabbitMQ Connection Debugging

The RabbitMQ helper now includes enhanced debug logging to help troubleshoot connection issues. When connecting to RabbitMQ, the system outputs detailed connection information to the console.

### Debug Output

When establishing a connection, you'll see:

```
🔗 Attempting to connect to RabbitMQ...
   Host: your-host.lmq.cloudamqp.com
   Port: 5671
   VHost: your-vhost
   User: your-username
   SSL: Enabled
   Connecting...
   Declaring queue: linkedin_profiles
✓ Connected to RabbitMQ at your-host.lmq.cloudamqp.com:5671 (SSL: True)
```

### Connection Failure Details

If connection fails, the system provides detailed error information:

```
✗ Failed to connect to RabbitMQ: [Error message]
   Error type: ConnectionError
[Full stack trace]
```

### What's Logged

The debug output includes:
- **Host**: RabbitMQ server hostname
- **Port**: Connection port (5671 for SSL, 5672 for plain)
- **VHost**: Virtual host path
- **User**: Authentication username
- **SSL Status**: Whether SSL/TLS is enabled
- **Queue Declaration**: Confirmation of queue setup
- **Error Type**: Exception class name on failure
- **Stack Trace**: Full traceback for debugging

### Use Cases

This enhanced logging helps diagnose:
- Incorrect credentials or host configuration
- SSL/TLS connection issues
- Network connectivity problems
- Queue declaration failures
- Authentication errors
- Firewall or port blocking

### Configuration

No additional configuration needed - debug logging is enabled by default in the `RabbitMQManager` class.

**Recent Update: March 6, 2026**
- Added comprehensive connection debug logging
- Included SSL status in connection output
- Added error type identification for faster troubleshooting
- Enhanced queue declaration confirmation
