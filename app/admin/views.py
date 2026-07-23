from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AdminUserSummary:
    username: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminUserView(AdminUserSummary):
    pass


@dataclass(frozen=True, slots=True)
class AdminUserPage:
    items: tuple[AdminUserSummary, ...]
    page: int
    per_page: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class AdminProductSummary:
    id: str
    title: str
    seller_username: str
    price: int
    status: str
    restore_status: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminProductView(AdminProductSummary):
    pass


@dataclass(frozen=True, slots=True)
class AdminProductPage:
    items: tuple[AdminProductSummary, ...]
    page: int
    per_page: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class AdminReportSummary:
    id: str
    reporter_username: str
    target_type: str
    target_display_name: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminReportView:
    id: str
    reporter_username: str
    target_type: str
    target_display_name: str
    reason: str
    status: str
    reviewer_username: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminReportPage:
    items: tuple[AdminReportSummary, ...]
    page: int
    per_page: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class AdminMessageView:
    id: str
    sender_username: str
    scope: str
    body: str
    is_hidden: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminMessagePage:
    items: tuple[AdminMessageView, ...]
    page: int
    per_page: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class AdminTransferView:
    id: str
    sender_username: str
    recipient_username: str
    amount: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminTransferPage:
    items: tuple[AdminTransferView, ...]
    page: int
    per_page: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class AdminAuditLogView:
    actor_username: str | None
    action: str
    target_type: str
    target_id: str | None
    details: tuple[tuple[str, str | int | bool | None], ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminAuditLogPage:
    items: tuple[AdminAuditLogView, ...]
    page: int
    per_page: int
    total: int
    pages: int
