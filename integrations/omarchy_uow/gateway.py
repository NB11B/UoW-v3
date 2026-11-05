"""Foreground Unix socket gateway to the bounded UoW service."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socketserver

from .service import Service
from uow.state import canonical_json


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        while line := self.rfile.readline(65538):
            if len(line) > 65536:
                response = {"decision": "DENIED", "reason": "INPUT_TOO_LARGE", "receipt": None}
                self.wfile.write((canonical_json(response) + "\n").encode())
                return
            try:
                request = json.loads(line)
                response = self.server.service.handle(request)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
                response = {"decision": "DENIED", "reason": "INVALID_REQUEST", "receipt": None}
            self.wfile.write((canonical_json(response) + "\n").encode())


class Gateway(socketserver.UnixStreamServer):
    def __init__(self, path: Path, db: Path, policy: dict, tokens: dict):
        self.path = Path(path)
        self.db, self.policy, self.tokens = db, policy, tokens
        if self.path.exists() or self.path.is_symlink():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        old_umask = os.umask(0o077)
        try:
            super().__init__(str(self.path), _Handler)
        finally:
            os.umask(old_umask)
        self.socket_inode = self.path.stat().st_ino

    def serve_forever(self, poll_interval: float = 0.1) -> None:
        try:
            self.service = Service(self.db, self.policy, self.tokens)
        except Exception:
            self.server_close()
            raise
        try:
            super().serve_forever(poll_interval=poll_interval)
        finally:
            self.service.close()

    def server_close(self) -> None:
        super().server_close()
        if self.path.exists() and getattr(self, "socket_inode", None) == self.path.stat().st_ino:
            self.path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tokens", type=Path, required=True)
    args = parser.parse_args()
    if args.tokens.stat().st_mode & 0o077:
        parser.error("token file must have mode 0600")
    gateway = Gateway(args.socket, args.db, json.loads(args.policy.read_text()), json.loads(args.tokens.read_text()))
    try:
        gateway.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        gateway.server_close()


if __name__ == "__main__":
    main()
