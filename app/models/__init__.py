"""
models/ package — all database tables in one place.

Each file groups related models by domain:
  user.py        → User, InvitationToken
  service.py     → Service, ProviderService, CancellationPolicy
  appointment.py → Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory
  payment.py     → Payment
  messaging.py   → Message
  medical.py     → MedicalRecord, Prescription, Review

Importing from here works exactly as before:
  from app.models import User, Appointment, Payment  ✓
"""
from app.extensions import db
from .user        import User, InvitationToken
from .service     import Service, ProviderService, CancellationPolicy, SERVICE_TAGS
from .appointment import Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory
from .payment     import Payment
from .messaging   import Message
from .medical     import MedicalRecord, Prescription, Review
from .feedback    import Feedback
from .telegram_session import TelegramSession

# Backward-compatible alias (old code may still use NurseService)
NurseService = ProviderService
