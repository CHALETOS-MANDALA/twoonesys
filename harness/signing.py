"""CASCADE - Identita' di firma persistente, con storico delle chiavi.

Un certificato firmato con una chiave rigenerata a ogni avvio non e'
verificabile dopo un riavvio: l'artefatto che esiste per rendere auditabile
una decisione smette di funzionare esattamente quando serve (dopo il fatto).

Due proprieta':

* **persistenza** - la coppia di chiavi vive in un file, non nel processo;
* **storico** - le chiavi PUBBLICHE passate restano registrate, quindi una
  rotazione non invalida i certificati gia' emessi. Il certificato porta il
  proprio `key_id` e il verificatore sa quale chiave usare.

La chiave privata NON deve finire in un repository: il percorso di default e'
`run/`, che questo modulo protegge con un `.gitignore` alla prima scrittura.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .a2a_protocol import generate_keypair, sign_bytes, verify_bytes

DEFAULT_STORE_ENV = "CASCADE_KEY_STORE"
DEFAULT_STORE = Path(__file__).resolve().parent / "run" / "signing_key.json"
DEFAULT_PUBLIC_KEYS = Path(__file__).resolve().parent / "run" / "public_keys.json"


def _key_id(public_bytes: bytes) -> str:
    """Identificatore stabile e pubblico della chiave (non un segreto)."""
    import hashlib
    return hashlib.sha256(public_bytes).hexdigest()[:16]


@dataclass(frozen=True)
class SigningIdentity:
    key_id: str
    private_bytes: bytes
    public_bytes: bytes

    @classmethod
    def generate(cls) -> "SigningIdentity":
        priv, pub = generate_keypair()
        return cls(key_id=_key_id(pub), private_bytes=priv, public_bytes=pub)

    # -- persistenza ------------------------------------------------------- #
    @classmethod
    def load_or_create(cls, path: str | os.PathLike | None = None) -> "SigningIdentity":
        """Carica l'identita' dal file; se manca, la crea e la salva.

        E' il gesto che rende un certificato verificabile dopo un riavvio.
        """
        p = Path(path or os.environ.get(DEFAULT_STORE_ENV) or DEFAULT_STORE)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            pub = bytes.fromhex(data["public_key"])
            ident = cls(key_id=data.get("key_id") or _key_id(pub),
                        private_bytes=bytes.fromhex(data["private_key"]),
                        public_bytes=pub)
            return ident
        ident = cls.generate()
        ident.save(p)
        return ident

    def save(self, path: str | os.PathLike) -> "SigningIdentity":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # la cartella della chiave non entra mai in un repository
        gi = p.parent / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        p.write_text(json.dumps({
            "key_id": self.key_id,
            "private_key": self.private_bytes.hex(),
            "public_key": self.public_bytes.hex(),
        }, sort_keys=True), encoding="utf-8")
        try:                                  # best effort: POSIX
            p.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pass
        return self

    # -- uso --------------------------------------------------------------- #
    def sign(self, payload: bytes) -> bytes:
        return sign_bytes(self.private_bytes, payload)


class KeyRegistry:
    """Storico delle chiavi pubbliche: una rotazione non invalida il passato."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path is not None else None
        self._keys: dict[str, bytes] = {}
        if self.path is not None and self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._keys = {k: bytes.fromhex(v) for k, v in data.items()}

    def register(self, identity_or_public: SigningIdentity | bytes) -> str:
        if isinstance(identity_or_public, SigningIdentity):
            kid, pub = identity_or_public.key_id, identity_or_public.public_bytes
        else:
            pub = identity_or_public
            kid = _key_id(pub)
        self._keys[kid] = pub
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({k: v.hex() for k, v in self._keys.items()}, sort_keys=True),
                encoding="utf-8")
        return kid

    def public_for(self, key_id: str) -> bytes | None:
        return self._keys.get(key_id)

    def verify(self, key_id: str, payload: bytes, signature: bytes) -> bool:
        pub = self.public_for(key_id)
        if pub is None:
            return False            # chiave sconosciuta: mai "valido per default"
        return verify_bytes(pub, payload, signature)

    def known(self) -> Mapping[str, bytes]:
        return dict(self._keys)

    def __len__(self) -> int:
        return len(self._keys)
