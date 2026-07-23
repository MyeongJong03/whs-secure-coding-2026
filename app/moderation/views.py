from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReportTargetView:
    target_type: str
    display_name: str


@dataclass(frozen=True, slots=True)
class OwnReportView:
    target_type: str
    target_display_name: str
    reason: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OwnReportPage:
    items: tuple[OwnReportView, ...]
    page: int
    per_page: int
    total: int
    pages: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int | None:
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self) -> int | None:
        return self.page + 1 if self.has_next else None
