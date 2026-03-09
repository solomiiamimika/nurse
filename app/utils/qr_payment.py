"""
EPC QR code generator for SEPA bank transfers.

The EPC QR standard (European Payments Council) allows banking apps
to pre-fill transfer details when a customer scans the code.
"""
import io
import base64
import re

import segno


def _sanitise_iban(iban: str) -> str:
    """Remove spaces and uppercase."""
    return re.sub(r'\s+', '', iban).upper()


def generate_epc_qr(
    iban: str,
    beneficiary_name: str,
    amount: float,
    reference: str = '',
    bic: str = '',
) -> str:
    """
    Generate an EPC QR code as a base64-encoded PNG data URI.

    Args:
        iban: Beneficiary IBAN (e.g. 'DE89370400440532013000')
        beneficiary_name: Account holder name (max 70 chars)
        amount: Amount in EUR (e.g. 25.50)
        reference: Payment reference / description (max 140 chars)
        bic: BIC/SWIFT code (optional, 8 or 11 chars)

    Returns:
        Base64 data URI string: 'data:image/png;base64,...'
    """
    iban_clean = _sanitise_iban(iban)
    name = beneficiary_name[:70]
    ref = reference[:140]

    # EPC QR payload — GPC 069-12, version 002
    lines = [
        'BCD',                          # Service Tag
        '002',                          # Version
        '1',                            # Character set (UTF-8)
        'SCT',                          # Identification code
        bic,                            # BIC (optional)
        name,                           # Beneficiary name
        iban_clean,                     # IBAN
        f'EUR{amount:.2f}',            # Amount
        '',                             # Purpose (AT-44)
        ref,                            # Remittance info (unstructured)
        '',                             # Info to beneficiary
    ]
    payload = '\n'.join(lines)

    qr = segno.make(payload, error='m')
    buf = io.BytesIO()
    qr.save(buf, kind='png', scale=8, border=2)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


def validate_iban(iban: str) -> bool:
    """Basic IBAN format validation (length + alphanumeric)."""
    clean = _sanitise_iban(iban)
    if len(clean) < 15 or len(clean) > 34:
        return False
    if not re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]+$', clean):
        return False
    return True
