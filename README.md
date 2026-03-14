# Human-Me — Service Marketplace Platform

A full-stack service marketplace connecting clients with providers (nurses, caregivers, handypeople) for on-demand home services. Includes web app, mobile app, and Telegram bot.

**Live:** [human-me.com](https://human-me.com)

---

## Features

- **Appointment booking** — direct booking or open requests with provider bidding
- **Real-time messaging** — WebSocket chat with text, audio, video, photos, files
- **Payments** — Stripe (cards), QR SEPA bank transfers, cash
- **Reviews & ratings** — bidirectional 5-star system
- **Multi-role** — users can be both client and provider, switch roles freely
- **Young helpers** — support for 13-17 year olds with parental consent (JArbSchG compliant)
- **Telegram bot** — full appointment management via Telegram
- **Multi-language** — English, Ukrainian, German, Polish
- **Provider discovery** — search by rating, location, service type, tags
- **Gamification** — user levels (Newcomer → Legend) based on completed orders
- **Verification** — email, phone, ID document, Stripe KYC

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1, SQLAlchemy 2.0, PostgreSQL (Supabase) |
| Real-time | Flask-SocketIO + eventlet |
| Auth | Flask-Login, JWT (mobile), Google OAuth2 |
| Payments | Stripe, SEPA QR (segno) |
| Email | Flask-Mail + Brevo SMTP |
| Storage | Supabase Storage (S3-compatible) |
| Frontend | Jinja2 + Bootstrap + vanilla JS |
| Mobile | React Native 0.81 + Expo 54 + TypeScript |
| Bot | Telegram Bot API (webhooks + polling) |
| Server | Gunicorn + Nginx |
| CI/CD | GitHub Actions (auto-deploy on push to main) |

---

## Project Structure

```
nurse/
├── app/
│   ├── __init__.py              # App factory, extensions, config
│   ├── config.py                # Settings from .env
│   ├── extensions.py            # Flask extensions init
│   ├── models/                  # SQLAlchemy models
│   │   ├── user.py              # User, InvitationToken, DeletedAccount
│   │   ├── service.py           # Service, ProviderService, CancellationPolicy
│   │   ├── appointment.py       # Appointment, ClientSelfCreatedAppointment, RequestOfferResponse
│   │   ├── payment.py           # Payment
│   │   ├── messaging.py         # Message
│   │   ├── medical.py           # MedicalRecord, Prescription, Review
│   │   ├── favorite.py          # Favorite, FavoriteShareToken
│   │   └── feedback.py          # Feedback
│   ├── routes/
│   │   ├── auth.py              # Registration, login, OAuth, password reset
│   │   ├── api_auth.py          # JWT API for mobile
│   │   ├── main.py              # Home, search, legal pages
│   │   ├── owner.py             # Admin dashboard
│   │   ├── client/              # Client: dashboard, appointments, payments, profile
│   │   └── provider/            # Provider: dashboard, appointments, services, finances
│   ├── telegram/                # Telegram bot
│   │   ├── handlers.py          # Command & callback handlers
│   │   ├── conversations.py     # Multi-step conversation flows
│   │   ├── keyboards.py         # Inline keyboards
│   │   ├── notifications.py     # Push notifications
│   │   └── webhook.py           # Webhook route
│   ├── templates/               # Jinja2 HTML (42 templates)
│   ├── static/                  # CSS, images, uploads
│   └── utils/
│       └── qr_payment.py        # EPC QR code generator
├── app_mobile/                  # React Native / Expo mobile app
│   ├── app/                     # File-based routing (Expo Router)
│   │   ├── (auth)/              # Login, register
│   │   ├── (client-tabs)/       # Client navigation
│   │   └── (provider-tabs)/     # Provider navigation
│   ├── components/              # Reusable components
│   ├── contexts/                # AuthContext, I18nContext
│   └── i18n/                    # Translations
├── migrations/                  # Alembic DB migrations
├── translations/                # Babel i18n (en, uk, de, pl)
├── .github/workflows/deploy.yml # Auto-deploy CI/CD
├── requirements.txt             # Python dependencies
└── run.py                       # Entry point
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL (or Supabase account)
- Node.js 18+ (for mobile app)
- Stripe account
- Supabase project (for file storage)

### Backend

```bash
# Clone
git clone https://github.com/solomiiamimika/nurse.git
cd nurse

# Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values (see Environment Variables below)

# Run database migrations
flask db upgrade

# Start development server
python run.py
```

The app will be available at `http://127.0.0.1:5000`.

### Mobile App

```bash
cd app_mobile
npm install
npx expo start
```

Use Expo Go app on your phone or press `a` for Android / `i` for iOS emulator.

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Flask
SECRET_KEY=your-secret-key
BASE_URL=http://127.0.0.1:5000

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Google OAuth2
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...

# Stripe Payments
STRIPE_PUBLIC_KEY=pk_...
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (Brevo SMTP)
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=...
MAIL_PASSWORD=...
MAIL_DEFAULT_SENDER=noreply@human-me.com

# Supabase (file storage)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=...

# Telegram Bot
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_NAME=...

# JWT (mobile API)
JWT_SECRET_KEY=...
```

---

## Deployment

Production runs on a VPS with Nginx + Gunicorn. Deployment is automated via GitHub Actions — every push to `main` triggers:

1. SSH into production server
2. `git pull origin main`
3. `pip install -r requirements.txt`
4. `systemctl restart gunicorn.service`

### Server details

- **Path:** `/var/www/human-me.com/nurse`
- **Venv:** `/var/www/human-me.com/venv`
- **Process manager:** systemd (`gunicorn.service`)
- **Reverse proxy:** Nginx

---

## Database Models

| Model | Description |
|-------|-------------|
| `User` | Users with roles (client/provider/owner), verification, Stripe/Telegram IDs |
| `Service` | Standard service catalog |
| `ProviderService` | Provider's offered services with custom pricing, tags, deposit % |
| `Appointment` | Direct bookings (client → provider) |
| `ClientSelfCreatedAppointment` | Open requests (client posts, providers bid) |
| `RequestOfferResponse` | Provider bids on open requests |
| `Payment` | Payment records with Stripe integration |
| `Message` | Chat messages (text, media, proposals) |
| `Review` | Bidirectional ratings and reviews |
| `Favorite` | Client's saved providers |
| `TelegramSession` | Bot conversation state |
| `Feedback` | Bug reports and suggestions |

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/api/register` | Mobile registration (JWT) |
| POST | `/auth/api/login` | Mobile login (JWT) |
| POST | `/login` | Web login |
| POST | `/register` | Web registration |

### Client
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/client/dashboard` | Client dashboard |
| GET | `/client/appointments` | List appointments |
| POST | `/client/pay_qr` | Mark QR payment |
| POST | `/client/pay_cash` | Mark cash payment |
| GET | `/client/qr_code/<type>/<id>` | Generate QR code |

### Provider
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/provider/dashboard` | Provider dashboard |
| GET | `/provider/finances` | Earnings & payouts |
| POST | `/provider/services` | Manage services |

### Telegram
| POST | `/telegram/webhook` | Bot webhook endpoint |

---

## Appointment Flow

```
Client books provider          Client posts request
        │                              │
        v                              v
   [scheduled]                    [pending]
        │                              │
   Provider confirms              Providers send offers
        │                              │
        v                              v
   [confirmed]                    [accepted]
        │                              │
   Client pays                    Client pays
   (Stripe/QR/Cash)              (Stripe/QR/Cash)
        │                              │
        v                              v
   [confirmed_paid]               [authorized]
        │                              │
   Provider arrives               Provider arrives
        │                              │
        v                              v
   [in_progress]                  [in_progress]
        │                              │
   Provider submits work          Provider submits work
        │                              │
        v                              v
   [work_submitted]               [work_submitted]
        │                              │
   Client approves                Client approves
   (or auto after 48h)           (or auto after 48h)
        │                              │
        v                              v
   [completed]                    [completed]
```

---

## License

Private project. All rights reserved.
