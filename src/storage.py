"""
Agent Bazaar - Encrypted Storage Layer
Fernet-encrypted JSON file I/O. All data-at-rest is encrypted.
Key source: BAZAAR_ENCRYPTION_KEY env var, or auto-generated in data/.key.
"""
import json
import os
import base64
from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
KEY_FILE = os.path.join(DATA_DIR, ".key")

_cipher = None
_disabled = False  # fallback: plaintext if encryption fails


def _get_cipher() -> Fernet | None:
    """Lazy-load encryption cipher. Returns None if disabled."""
    global _cipher, _disabled
    if _disabled:
        return None
    if _cipher is not None:
        return _cipher

    # Try env var first
    env_key = os.environ.get("BAZAAR_ENCRYPTION_KEY", "")
    if env_key:
        try:
            _cipher = Fernet(env_key.encode())
            return _cipher
        except Exception:
            pass

    # Try key file
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "rb") as f:
                _cipher = Fernet(f.read())
            return _cipher
        except Exception:
            pass

    # Auto-generate key (development mode)
    key = Fernet.generate_key()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    _cipher = Fernet(key)
    print(f"🔑 Auto-generated encryption key at {KEY_FILE}")
    return _cipher


def setup_encryption(env_key: str = None) -> bool:
    """Explicitly configure encryption. Call from server startup."""
    if env_key:
        os.environ["BAZAAR_ENCRYPTION_KEY"] = env_key
    global _cipher, _disabled
    _cipher = None
    _disabled = False
    try:
        _get_cipher()
        return True
    except Exception:
        _disabled = True
        return False


def disable_encryption():
    """Fallback to plaintext storage (for migration/testing)."""
    global _disabled
    _disabled = True


def _encrypt(plaintext: str) -> bytes:
    """Encrypt string → bytes."""
    cipher = _get_cipher()
    if cipher is None:
        return plaintext.encode()
    return cipher.encrypt(plaintext.encode())


def _decrypt(ciphertext: bytes) -> str:
    """Decrypt bytes → string."""
    cipher = _get_cipher()
    if cipher is None:
        return ciphertext.decode()
    return cipher.decrypt(ciphertext).decode()


def load_json(filename: str) -> dict:
    """Load and decrypt a JSON file. Returns empty dict if not found."""
    enc_path = _enc_path(filename)
    if not os.path.exists(enc_path):
        # Try legacy unencrypted file (migration)
        legacy = os.path.join(DATA_DIR, filename)
        if os.path.exists(legacy) and filename.endswith(".json"):
            with open(legacy, "r") as f:
                data = json.load(f)
            # Migrate immediately
            save_json(filename, data)
            os.remove(legacy)
            return data
        return {}

    with open(enc_path, "rb") as f:
        raw = f.read()

    if not raw:
        return {}

    try:
        plaintext = _decrypt(raw)
    except InvalidToken:
        # Corrupted or legacy plaintext
        try:
            plaintext = raw.decode()
            # Migrate
            data = json.loads(plaintext)
            save_json(filename, data)
            return data
        except Exception:
            return {}

    return json.loads(plaintext)


def save_json(filename: str, data: dict):
    """Encrypt and save a JSON file atomically."""
    plaintext = json.dumps(data, ensure_ascii=False, indent=2)
    ciphertext = _encrypt(plaintext)

    enc_path = _enc_path(filename)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Atomic write: temp file → rename
    tmp_path = enc_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(ciphertext)
    os.replace(tmp_path, enc_path)


def _enc_path(filename: str) -> str:
    """Get the encrypted file path (adds .enc suffix for JSON files)."""
    if filename.endswith(".json"):
        return os.path.join(DATA_DIR, filename[:-5] + ".enc")
    if filename.endswith(".jsonl"):
        return os.path.join(DATA_DIR, filename[:-6] + ".jsonl.enc")
    return os.path.join(DATA_DIR, filename)


class EncryptedJSONL:
    """Encrypted JSONL (append-only) file handler."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.enc_path = _enc_path(filename)
    
    def append(self, record: dict):
        """Append one JSON record, encrypt the file atomically."""
        # Read existing lines
        existing = self.read_all()
        existing.append(record)
        self._write_all(existing)
    
    def read_all(self) -> list[dict]:
        """Read all records."""
        if not os.path.exists(self.enc_path):
            # Legacy migration
            legacy = os.path.join(DATA_DIR, self.filename)
            if os.path.exists(legacy):
                lines = []
                with open(legacy, "r") as f:
                    for line in f:
                        try:
                            lines.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
                self._write_all(lines)
                os.remove(legacy)
                return lines
            return []
        
        try:
            plaintext = _decrypt(open(self.enc_path, "rb").read())
        except (InvalidToken, UnicodeDecodeError):
            plaintext = open(self.enc_path, "rb").read().decode()

        lines = []
        for line in plaintext.strip().split("\n"):
            if line.strip():
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return lines
    
    def _write_all(self, records: list[dict]):
        """Write all records as encrypted JSONL."""
        lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
        ciphertext = _encrypt(lines)
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = self.enc_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(ciphertext)
        os.replace(tmp, self.enc_path)
