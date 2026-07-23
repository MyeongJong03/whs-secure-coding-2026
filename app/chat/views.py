from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatMessageView:
    id: str
    sender_username: str
    body: str
    created_at_iso: str


@dataclass(frozen=True, slots=True)
class ChatMessagePage:
    items: tuple[ChatMessageView, ...]
    page: int
    per_page: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool
    prev_num: int | None
    next_num: int | None


@dataclass(frozen=True, slots=True)
class DirectConversationSummary:
    id: str
    counterpart_username: str
    counterpart_is_active: bool
    created_at_iso: str


@dataclass(frozen=True, slots=True)
class DirectConversationPage:
    items: tuple[DirectConversationSummary, ...]
    page: int
    per_page: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool
    prev_num: int | None
    next_num: int | None


@dataclass(frozen=True, slots=True)
class DirectConversationView:
    id: str
    counterpart_username: str
    counterpart_is_active: bool
