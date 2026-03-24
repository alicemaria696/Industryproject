# Assessment System

A modular assessment platform with role-based workflows for **Admin, Teacher, and Student**, built using Flask + MySQL and split into microservices for registration, OTP authentication, and core assessment features.

## Modules

- **auth-registration** (`:5001`)  
  Registers users and creates role-specific records.
- **auth-otp** (`:5002`)  
  OTP generation/verification with JWT issuance (Fast2SMS integration).
- **core-assessment** (`:5000`)  
  Main web app for classes, subjects, assignments, submissions, scoring, reports, and live tests.
- **mysql** (`:3307` host mapped to MySQL `3306` in container)

## Key Features

- Role-based access (Admin / Teacher / Student)
- Class and subject management
- Theory assignments (document upload, keyword/match-based evaluation)
- Script assignments (test-case based auto-evaluation)
- Live tests with:
  - Timed attempts
  - Proctoring events (focus/tab tracking)
  - Recording upload per attempt
  - Teacher review and manual mark edits
- Performance dashboards and report views
- Export/download support for teacher result analysis

## Project Structure

```text
assesmentsystem/
├── docker-compose.yml
├── mysql-init.sql
├── requirements.txt
├── auth-registration/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── auth-otp/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── core-assessment/
    ├── Dockerfile
    ├── requirements.txt
    ├── flask_app/
    │   ├── run.py
    │   └── app/
    │       ├── __init__.py
    │       ├── models.py
    │       ├── routes.py
    │       └── templates/
    └── uploads/
```

## Tech Stack

- **Backend:** Flask, Flask-SQLAlchemy
- **Database:** MySQL 8
- **Auth/Token:** OTP + JWT
- **Containerization:** Docker, Docker Compose
- **Others:** PyMySQL, mysql-connector-python, PyPDF2, docx2txt, spaCy, scikit-learn

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Git
- (Optional for OTP SMS) Fast2SMS API key

## Environment Variables

The compose file already injects DB variables for all services.  
For OTP SMS delivery, set this before startup:

### Windows PowerShell

```powershell
$env:FAST2SMS_API_KEY="your_fast2sms_api_key"
```

### Linux/macOS

```bash
export FAST2SMS_API_KEY="your_fast2sms_api_key"
```

> If `FAST2SMS_API_KEY` is not set, OTP generation still works and OTP is returned in API response for testing.

## Run with Docker Compose (Recommended)

From project root (`assesmentsystem`):

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up -d --build
```

Stop services:

```bash
docker compose down
```

Stop and remove DB volume (full reset):

```bash
docker compose down -v
```

## Service Endpoints

- Core app: `http://localhost:5000`
- Auth registration API: `http://localhost:5001`
- Auth OTP API: `http://localhost:5002`
- MySQL host port: `localhost:3307`

## Database Bootstrapping

`mysql-init.sql` is auto-applied on MySQL container initialization. It:

- Creates database `assessment_system`
- Creates user `devuser` / password `dev@user1`
- Creates core tables (`teacher`, `student`, `class`, `subject`, `assignment`, `result`, `script_submission`, `live_test_attempt`, etc.)

## Data Persistence

- MySQL data is persisted in Docker volume: `mysql_data`
- Uploaded files are persisted via bind mount:
  - Host: `./core-assessment/uploads`
  - Container: `/app/uploads`

This includes live-test recordings, uploaded submissions, and related artifacts.

## OTP API Quick Test

### Send OTP

```bash
curl -X POST http://localhost:5002/send-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"9876543210"}'
```

### Verify OTP

```bash
curl -X POST http://localhost:5002/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"9876543210", "otp":"123456"}'
```

### Register user

```bash
curl -X POST http://localhost:5001/register \
  -H "Content-Type: application/json" \
  -d '{"reg_id":"S1001","phone":"9876543210","password":"test123","role":"S"}'
```

## Local (Non-Docker) Run (Optional)

You can also run each service manually with Python virtual environments, but Docker Compose is recommended to avoid dependency/version mismatch.

- `auth-registration`: runs on port `5001`
- `auth-otp`: runs on port `5002`
- `core-assessment/flask_app/run.py`: runs on port `5000`

Ensure MySQL is running and DB credentials match environment variables.

## Common Issues & Fixes

- **`Import could not be resolved` in editor**  
  Usually local interpreter mismatch; containers still run correctly when dependencies are installed inside Docker.

- **OTP SMS not received**  
  Verify `FAST2SMS_API_KEY`; check logs for Fast2SMS response.

- **Recordings not visible after rebuild**  
  Ensure `core-assessment` volume mount exists in `docker-compose.yml`:
  `./core-assessment/uploads:/app/uploads`

- **Fresh schema not applying**  
  Remove DB volume and restart:
  `docker compose down -v && docker compose up --build`

## Security Note

Current settings are development-friendly (example secrets and debug defaults). For production:

- Rotate secrets (`SECRET_KEY`, JWT secret)
- Use HTTPS and secure cookies
- Lock down CORS and service exposure
- Avoid returning OTP in API responses
- Use managed secret storage

## License

Add your preferred license (MIT/Apache-2.0/etc.) before publishing publicly.

---

If you want, I can also add:

- a `.env.example` file
- API collection (`Postman`/`Thunder Client`)
- a minimal deployment section (Render/Azure/AWS)
