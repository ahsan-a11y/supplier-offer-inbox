"""Settings, read once from environment variables (a .env file is loaded if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# USD per million tokens (input, output). Used only for cost reporting.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


@dataclass(frozen=True)
class Settings:
    imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_password: str = os.getenv("IMAP_PASSWORD", "")
    imap_folder: str = os.getenv("IMAP_FOLDER", "INBOX")
    classify_model: str = os.getenv("CLASSIFY_MODEL", "claude-haiku-5-5")
    extract_model: str = os.getenv("EXTRACT_MODEL", "claude-sonnet-5-5")
    extract_effort: str = os.getenv("EXTRACT_EFFORT", "medium")
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    # Rows below this confidence are flagged for human review.
    review_threshold: float = float(os.getenv("REVIEW_THRESHOLD", "0.8"))
    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "3"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "offers.db"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"


settings = Settings()


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
