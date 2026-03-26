import os
import sys

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
except ImportError:
    print("Please install pywebpush: pip install pywebpush")
    sys.exit(1)

def generate_keys():
    # Vapid.generate() doesn't actually exist to generate keys directly easily, we can use os.urandom or EC keys
    import ecdsa
    import base64
    from ecdsa.keys import SigningKey
    from ecdsa.curves import NIST256p
    from pywebpush import webpush

    # Generate an ECDSA P-256 private key
    sk = SigningKey.generate(curve=NIST256p)
    vk = sk.verifying_key

    # Extract keys and base64-encode them
    private_key_bytes = sk.to_string()
    public_key_bytes = b'\x04' + vk.to_string() # Uncompressed format

    # URL-safe base64 without padding
    def b64url(data):
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

    private_key_b64 = b64url(private_key_bytes)
    public_key_b64 = b64url(public_key_bytes)

    print("\n--- VAPID Keys Generated ---")
    print(f"VAPID_PUBLIC_KEY={public_key_b64}")
    print(f"VAPID_PRIVATE_KEY={private_key_b64}")
    print(f"VAPID_CLAIM_EMAIL=mailto:admin@sinlongheng.com")
    print("\nAdd these variables to your .env file on PythonAnywhere.")

if __name__ == "__main__":
    generate_keys()
