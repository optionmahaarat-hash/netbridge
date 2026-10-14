"""Creates the signing key pair ONCE.
   keys/update_private.key   -> secret. Never share, never put it in a zip. BACK IT UP: without it you cannot publish updates.
   assets/update_pubkey.txt  -> public. Goes inside the app; the app only installs updates signed by the private key."""
import base64, sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
PRIV, PUB = ROOT / "keys" / "update_private.key", ROOT / "assets" / "update_pubkey.txt"


def main():
    if PRIV.exists():
        print("Signing key already exists:", PRIV)
        if not PUB.exists():    # rebuild the public half from the private one
            k = serialization.load_pem_private_key(PRIV.read_bytes(), None)
            PUB.write_text(base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
            print("Rebuilt", PUB)
        return
    k = Ed25519PrivateKey.generate()
    PRIV.parent.mkdir(exist_ok=True)
    PRIV.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    PUB.write_text(base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
    print("NEW signing key created:", PRIV)
    print("  >>> BACK UP keys\\update_private.key somewhere safe (USB / password manager). Never share it. <<<")
    print("Public key written to", PUB)


if __name__ == "__main__":
    sys.exit(main())
