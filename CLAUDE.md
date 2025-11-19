# CLAUDE.md - AI Assistant Guidelines for CHT-OJ

## Project Overview

**CHT-OJ** (CHUYÊN HÀ TĨNH Online Judge) is a Vietnamese-language online judge platform for competitive programming, forked from [DMOJ](https://github.com/DMOJ/online-judge). It serves students at Hà Tĩnh Specialized High School.

**Live Instance:** https://oj.thptchuyenhatinh.edu.vn/

## Tech Stack

- **Backend:** Django 3.2.x (Python 3.12+)
- **Database:** MySQL with UTF-8MB4 encoding
- **Template Engine:** Jinja2 (via django-jinja)
- **Task Queue:** Celery with RabbitMQ (AMQP)
- **Caching:** Redis/Memcached
- **Frontend:** SCSS, Vanilla JS + jQuery, ACE.js code editor
- **WebSocket Server:** Node.js (for real-time updates)

## Project Structure

```
CHT-oj/
├── judge/                    # Main Django application
│   ├── admin/               # Django admin customizations
│   ├── bridge/              # Judge server communication
│   ├── contest_format/      # Contest scoring formats (IOI, ICPC, AtCoder, etc.)
│   ├── management/commands/ # Django management commands
│   ├── models/              # Database models (~3,200 lines)
│   │   ├── problem.py       # Problem entities
│   │   ├── submission.py    # Submission tracking
│   │   ├── contest.py       # Contest management
│   │   ├── profile.py       # User profiles & organizations
│   │   └── ...
│   ├── views/               # HTTP request handlers
│   │   ├── api/api_v2.py    # REST API
│   │   ├── problem.py       # Problem pages
│   │   ├── submission.py    # Submission views
│   │   ├── contests.py      # Contest views
│   │   └── ...
│   ├── tasks/               # Celery background tasks
│   ├── templatetags/        # Jinja2 custom filters
│   ├── utils/               # Utility modules
│   └── forms.py             # Django forms
├── dmoj/                    # Django project configuration
│   ├── settings.py          # Main settings
│   ├── urls.py              # URL routing
│   ├── celery.py            # Celery configuration
│   └── local_settings.py    # Local overrides (gitignored)
├── templates/               # Jinja2 templates (by feature)
├── resources/               # Frontend assets (SCSS, JS)
├── websocket/               # Node.js WebSocket server
├── locale/                  # i18n translations (en, vi)
├── scripts/                 # Utility scripts
└── .github/workflows/       # CI/CD pipelines
```

## Core Data Models

### Key Entities

- **Problem** (`judge/models/problem.py`): Problem definitions with metadata, limits, visibility settings
- **Submission** (`judge/models/submission.py`): User submissions with results (AC, WA, TLE, etc.)
- **Contest** (`judge/models/contest.py`): Contest configuration, participation, rankings
- **Profile** (`judge/models/profile.py`): User profiles, ratings, 2FA, preferences
- **Organization**: Teams/groups with membership and private content
- **Language** (`judge/models/runtime.py`): Programming language configurations
- **Judge**: Judge server registrations and status

### Result Codes

- **AC** - Accepted
- **WA** - Wrong Answer
- **TLE** - Time Limit Exceeded
- **MLE** - Memory Limit Exceeded
- **OLE** - Output Limit Exceeded
- **RTE** - Runtime Error
- **CE** - Compile Error
- **IE** - Internal Error
- **AB** - Aborted
- **SC** - Short Circuit

## Development Commands

### Running the Application

```bash
# Django development server
python manage.py runserver

# Run Celery worker
celery -A dmoj worker -l info

# Compile SCSS styles
./make_style.sh
```

### Database Operations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### Testing

```bash
# Run all tests
python manage.py test judge

# With coverage
coverage run --source=. manage.py test judge
coverage report
```

### Useful Management Commands

```bash
# Add a judge server
python manage.py addjudge <name> <auth_key>

# Create user
python manage.py adduser <username> <email>

# Generate API token
python manage.py generate_api_token <username>

# Import from Codeforces Polygon
python manage.py import_polygon_package <package_path>

# Generate translations
python manage.py makedmojmessages
python manage.py compilemessages
```

## Code Style & Conventions

### Python (Flake8)

- **Max line length:** 120 characters
- **Import style:** pycharm (stdlib, third-party, local)
- **Config file:** `.flake8`

```bash
# Run linter
flake8 judge/
```

Key rules:
- PEP 8 compliant with 120 char lines
- No wildcard imports except in `__init__.py`
- Migration files have relaxed rules

### JavaScript/Node.js (Prettier)

- **Indentation:** 2 spaces
- **Line width:** 100 characters
- **Quotes:** Double quotes
- **Semicolons:** Required
- **Trailing commas:** Always

```bash
# Format code
npx prettier --write websocket/
```

### General Conventions

1. **Use class-based views** for complex logic
2. **Prefer django-reversion** for models that need history tracking
3. **Use Celery tasks** for heavy/long-running operations
4. **Mark strings for translation** with `gettext_lazy()` or `_()`
5. **Use select_related/prefetch_related** for query optimization

## Testing Guidelines

- Tests are located in `judge/models/tests/`
- Use `CommonDataMixin` for shared test fixtures
- Test files follow pattern `test_<feature>.py`
- CI runs tests with MySQL database

## CI/CD Pipeline

GitHub Actions workflows in `.github/workflows/`:

1. **build.yml** - Main pipeline:
   - Flake8 linting
   - Unit tests with coverage
   - SCSS/CSS compilation

2. **compilemessages.yml** - Translation compilation
3. **updatemessages.yml** - Translation string extraction
4. **caniuse.yml** - Browser compatibility updates

## Key Configuration

### Environment Settings

Create `dmoj/local_settings.py` for local overrides:

```python
# Database
DATABASES['default']['USER'] = 'your_user'
DATABASES['default']['PASSWORD'] = 'your_password'

# Problem data directory (REQUIRED)
DMOJ_PROBLEM_DATA_ROOT = '/path/to/problems/'

# Judge bridge
BRIDGED_DJANGO_ADDRESS = [('localhost', 9999)]

# Cache (production)
CACHES['default']['BACKEND'] = 'django.core.cache.backends.redis.RedisCache'
```

### Important Settings

- `DMOJ_PROBLEM_DATA_ROOT` - Path to test case files (required)
- `DMOJ_SUBMISSION_LIMIT` - Concurrent submissions per user (default: 2)
- `VNOJ_TESTCASE_HARD_LIMIT` - Max testcases without permission (100)
- `VNOJ_PROBLEM_TIMELIMIT_LIMIT` - Max time limit (5 seconds)
- `DMOJ_REQUIRE_STAFF_2FA` - Mandatory 2FA for staff

## Security Considerations

### Authentication
- Two-factor auth: TOTP and WebAuthn/U2F
- Social auth via OAuth
- Pwned password checking

### Data Protection
- CSRF protection enabled
- HTML sanitization via Bleach
- XSS protection middleware
- Parameterized SQL queries (Django ORM)

### Sensitive Files (gitignored)
- `dmoj/local_settings.py`
- `dmoj/local_urls.py`
- `.env` files

## Internationalization

- Primary language: Vietnamese (`locale/vi/`)
- Secondary: English (`locale/en/`)
- Use `_()` or `gettext_lazy()` for translatable strings
- Translations in .po format (compiled to .mo)

## API

REST API v2 available at `/api/v2/`:
- Problems, Submissions, Contests
- Languages, Judges
- Users, Organizations, Ratings

Enable with `VNOJ_ENABLE_API = True`

## Common Development Tasks

### Adding a New View

1. Create view in `judge/views/<feature>.py`
2. Add URL pattern in `dmoj/urls.py`
3. Create template in `templates/<feature>/`
4. Add any required forms in `judge/forms.py`

### Adding a New Model

1. Define model in `judge/models/<module>.py`
2. Export in `judge/models/__init__.py`
3. Create migration: `python manage.py makemigrations`
4. Register with admin in `judge/admin/`
5. Consider adding to reversion tracking

### Modifying Contest Formats

Contest formats are in `judge/contest_format/`:
- Inherit from base format class
- Implement scoring and ranking logic
- Register in format registry

### Adding Background Tasks

1. Create task in `judge/tasks/<module>.py`
2. Use `@shared_task` decorator
3. Configure in Celery beat schedule if recurring

## Architecture Notes

### Judge Communication

- Bridge server handles judge-Django communication
- Custom binary protocol over TCP sockets
- Priority queue: CONTEST > REJUDGE > DEFAULT > BATCH

### Real-time Updates

- WebSocket server in Node.js (`websocket/daemon.js`)
- Event posting via AMQP or direct WebSocket
- Used for live submission status and leaderboards

### Caching Strategy

- Language runtime versions
- Full-text search results
- Math rendering (Mathoid)
- Use Redis in production

## Troubleshooting

### Common Issues

1. **Missing `local_settings.py`**: Copy from settings template
2. **Database encoding errors**: Ensure UTF-8MB4 charset
3. **Static files not loading**: Run `./make_style.sh`
4. **Judge not connecting**: Check bridge configuration

### Debug Mode

Set in `local_settings.py`:
```python
DEBUG = True
```

## Contributing

1. Follow flake8 style guidelines
2. Write tests for new features
3. Use Prettier for JS/Node code
4. Vietnamese translations welcome
5. See `contributing.md` for details

## Dependencies

### Python (requirements.txt)
Key packages: Django 3.2, Celery, django-jinja, martor, social-auth, webauthn, bleach

### Node.js (package.json)
Key packages: ws (WebSocket), postcss, sass

## Useful Links

- [DMOJ Documentation](https://docs.dmoj.ca/)
- [Django 3.2 Documentation](https://docs.djangoproject.com/en/3.2/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
