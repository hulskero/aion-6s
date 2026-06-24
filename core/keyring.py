"""Encrypted API key storage for AION-6S.

File format (config.key):
    magic    (4 bytes)  b"AKS1"
    version  (1 byte)   0x01
    salt     (16 bytes)
    nonce    (16 bytes)
    ciphertext (variable)
    hmac     (32 bytes) HMAC-SHA256 over header || ciphertext

Key derivation: PBKDF2-HMAC-SHA256(passphrase, salt, 200_000 iters, 64 bytes)
    -> enc_key (32 bytes) || mac_key (32 bytes)

Stream cipher: CTR-like using HMAC-SHA256
    block_i = HMAC(enc_key, nonce || i.to_bytes(4, 'big'))[:32]
    ciphertext = plaintext XOR concat(block_0, block_1, ...)

File permissions: 0600 (owner read/write only).
"""

import hashlib
import hmac
import os
import secrets
import sys

MAGIC = b"AKS1"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 16
HMAC_LEN = 32
PBKDF2_ITERS = 200_000
KEY_LEN = 64  # 32 enc + 32 mac


class KeyringError(Exception):
    """Raised on any keyring failure (wrong passphrase, tampered file, etc.)."""


def _derive_keys(passphrase, salt):
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    raw = hashlib.pbkdf2_hmac("sha256", passphrase, salt, PBKDF2_ITERS, dklen=KEY_LEN)
    return raw[:32], raw[32:]


def _keystream(enc_key, nonce, n):
    out = bytearray()
    counter = 0
    while len(out) < n:
        block = hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:n])


def encrypt_key(plaintext_key, passphrase):
    """Encrypt the API key. Returns a blob (bytes)."""
    if not isinstance(plaintext_key, str) or not plaintext_key:
        raise KeyringError("plaintext_key must be a non-empty string")
    if not isinstance(passphrase, str) or len(passphrase) < 4:
        raise KeyringError("passphrase must be at least 4 characters")

    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(NONCE_LEN)
    enc_key, mac_key = _derive_keys(passphrase, salt)

    pt = plaintext_key.encode("utf-8")
    ks = _keystream(enc_key, nonce, len(pt))
    ct = bytes(a ^ b for a, b in zip(pt, ks))

    header = MAGIC + bytes([VERSION]) + salt + nonce
    mac = hmac.new(mac_key, header + ct, hashlib.sha256).digest()
    return header + ct + mac


def decrypt_key(blob, passphrase):
    """Decrypt the blob. Returns the plaintext API key (str)."""
    if not isinstance(blob, (bytes, bytearray)):
        raise KeyringError("blob must be bytes")
    blob = bytes(blob)
    min_len = 4 + 1 + SALT_LEN + NONCE_LEN + HMAC_LEN
    if len(blob) < min_len:
        raise KeyringError("blob too short")

    if blob[:4] != MAGIC:
        raise KeyringError("bad magic (not an AKS1 file)")
    version = blob[4]
    if version != VERSION:
        raise KeyringError(f"unsupported version: {version}")

    salt = blob[5:5 + SALT_LEN]
    nonce = blob[5 + SALT_LEN:5 + SALT_LEN + NONCE_LEN]
    ct = blob[5 + SALT_LEN + NONCE_LEN:-HMAC_LEN]
    mac = blob[-HMAC_LEN:]

    _, mac_key = _derive_keys(passphrase, salt)
    header = MAGIC + bytes([VERSION]) + salt + nonce
    expected = hmac.new(mac_key, header + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise KeyringError("HMAC mismatch (wrong passphrase or tampered file)")

    enc_key, _ = _derive_keys(passphrase, salt)
    ks = _keystream(enc_key, nonce, len(ct))
    pt = bytes(a ^ b for a, b in zip(ct, ks))
    try:
        return pt.decode("utf-8")
    except UnicodeDecodeError as e:
        raise KeyringError(f"decrypted data is not valid UTF-8: {e}")


def save_key(key_path, api_key, passphrase):
    """Encrypt api_key and write atomically to key_path with mode 0600."""
    blob = encrypt_key(api_key, passphrase)
    tmp = key_path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, blob)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, key_path)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass


def load_key(key_path, passphrase):
    """Read key_path and decrypt."""
    with open(key_path, "rb") as f:
        blob = f.read()
    return decrypt_key(blob, passphrase)


def key_exists(key_path):
    """True if key_path exists and looks like a valid AKS1 file."""
    try:
        with open(key_path, "rb") as f:
            head = f.read(4)
        return head == MAGIC
    except OSError:
        return False


def prompt_passphrase(prompt="Passphrase: "):
    """Prompt once for a passphrase (no echo)."""
    try:
        import getpass
        pw = getpass.getpass(prompt)
    except Exception:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        pw = sys.stdin.readline().rstrip("\n")
    if not pw:
        raise KeyringError("empty passphrase")
    return pw


def prompt_passphrase_twice():
    """Prompt twice and verify match."""
    while True:
        pw1 = prompt_passphrase("Set key passphrase: ")
        pw2 = prompt_passphrase("Confirm passphrase: ")
        if pw1 == pw2:
            return pw1
        sys.stdout.write("Passphrases do not match. Try again.\n")
        sys.stdout.flush()


def migrate_from_plaintext(plaintext_key, key_path, passphrase):
    """Encrypt an existing plaintext key and write to key_path."""
    save_key(key_path, plaintext_key, passphrase)
