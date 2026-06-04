import bcrypt
import hashlib
import base64

def _prepare_password(password: str) -> bytes:
    """
    Hashes a password with SHA-256 first. 
    This safely condenses ANY password into 32 bytes, 
    bypassing bcrypt's 72-byte limit entirely.
    """
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.b64encode(digest)

def hash_password(password: str) -> str:
    """Hashes the password using raw bcrypt."""
    pwd_bytes = _prepare_password(password)
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    
    # Return as string so it easily saves to your database
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies the password using raw bcrypt."""
    pwd_bytes = _prepare_password(plain_password)
    hashed_bytes = hashed_password.encode('utf-8')
    
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)