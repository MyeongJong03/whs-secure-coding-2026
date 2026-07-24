from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WalletSummaryView:
    username: str
    balance: int


@dataclass(frozen=True, slots=True)
class TransferHistoryView:
    id: str
    direction: str
    counterpart_username: str
    amount: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TransferHistoryPage:
    items: tuple[TransferHistoryView, ...]
    page: int
    per_page: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool
    prev_num: int | None
    next_num: int | None


@dataclass(frozen=True, slots=True)
class TransferDetailView:
    id: str
    sender_username: str
    recipient_username: str
    direction: str
    amount: int
    created_at: datetime
