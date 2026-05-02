import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# 1. Generate the secure pair
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# 2. Encode for Web Push standards
private_val = private_key.private_numbers().private_value
vapid_private = base64.urlsafe_b64encode(private_val.to_bytes(32, 'big')).decode('utf-8').strip("=")
public_bytes = public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
vapid_public = base64.urlsafe_b64encode(public_bytes).decode('utf-8').strip("=")

# 3. Output the result for the .env file
print("\n" + "="*30)
print("SUCCESS! COPY THESE TWO LINES:")
print("="*30)
print(f"VAPID_PUBLIC_KEY={vapid_public}")
print(f"VAPID_PRIVATE_KEY={vapid_private}")
print("="*30)
