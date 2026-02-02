import secrets

def generate_secret_key():
    """Generates a secure random secret key."""
    return secrets.token_hex(24)

if __name__ == "__main__":
    print("Generated Secret Key:")
    print(generate_secret_key())
