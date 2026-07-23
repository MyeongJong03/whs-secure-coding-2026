import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import RLock


class ChatEventLimiter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] | None,
        message_burst_limit: int,
        message_burst_window: float,
        message_hourly_limit: int,
        join_limit: int,
        join_window: float,
    ) -> None:
        self._clock = clock or time.monotonic
        self._message_burst_limit = message_burst_limit
        self._message_burst_window = message_burst_window
        self._message_hourly_limit = message_hourly_limit
        self._join_limit = join_limit
        self._join_window = join_window
        self._messages: dict[str, deque[float]] = defaultdict(deque)
        self._joins: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    @staticmethod
    def _prune(timestamps: deque[float], cutoff: float) -> None:
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

    def consume_message(self, user_id: str) -> bool:
        now = self._clock()
        with self._lock:
            timestamps = self._messages[user_id]
            self._prune(timestamps, now - 3600)
            burst_count = sum(
                timestamp > now - self._message_burst_window for timestamp in timestamps
            )
            if (
                burst_count >= self._message_burst_limit
                or len(timestamps) >= self._message_hourly_limit
            ):
                return False
            timestamps.append(now)
            return True

    def consume_join(self, user_id: str) -> bool:
        now = self._clock()
        with self._lock:
            timestamps = self._joins[user_id]
            self._prune(timestamps, now - self._join_window)
            if len(timestamps) >= self._join_limit:
                return False
            timestamps.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._messages.clear()
            self._joins.clear()
