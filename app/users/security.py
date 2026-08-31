from hashlib import sha256


def hash_password(username: str, password: str) -> str:
    password_payload = f"{username}:{password}".encode("utf-8")
    return sha256(password_payload).hexdigest()
