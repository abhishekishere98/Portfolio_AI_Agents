import base64
import hashlib
import hmac
import getpass
import secrets


def encrypt_api_key(api_key: str, secret: str) -> str:
    if not api_key.strip():
        raise ValueError("api_key cannot be empty")
    if not secret.strip():
        raise ValueError("secret cannot be empty")

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 200000, dklen=32)
    ciphertext = bytes(
        byte ^ key[index % len(key)] ^ nonce[index % len(nonce)]
        for index, byte in enumerate(api_key.encode("utf-8"))
    )
    signature = hmac.new(key, salt + nonce + ciphertext, hashlib.sha256).digest()
    payload = salt + nonce + ciphertext + signature
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _prompt_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Input cannot be empty. Please try again.")


def main():
    print("Cloud API Key Encryption Utility")

    api_key = _prompt_non_empty("Enter cloud API key: ")

    encrypted = encrypt_api_key(
        api_key,
        "PRD_AGENT_SECRET_V1"
    )

    print("\nEncrypted key:")
    print(encrypted)


if __name__ == "__main__":
    main()