"""Generate a VAPID keypair for Web Push, printed as env-ready base64url strings.

Run ONCE per deployment; paste the output into the server's .env (NEVER commit):

    python scripts/gen_vapid.py

- VAPID_PUBLIC_KEY  → also the browser's applicationServerKey (65-byte point).
- VAPID_PRIVATE_KEY → the raw 32-byte private value; pywebpush signs with it.

Both are single-line base64url (no padding), safe for env vars.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_raw = priv.private_numbers().private_value.to_bytes(32, "big")
    pub_point = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"VAPID_PUBLIC_KEY={b64u(pub_point)}")
    print(f"VAPID_PRIVATE_KEY={b64u(priv_raw)}")
    print("VAPID_SUBJECT=mailto:support@blackvoltmobility.com")


if __name__ == "__main__":
    main()
