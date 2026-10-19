from typing import Protocol

class Importer(Protocol):
    def import_bytes(self, db, content: bytes) -> int:
        """Validate and atomically append portfolio snapshots."""
        ...
