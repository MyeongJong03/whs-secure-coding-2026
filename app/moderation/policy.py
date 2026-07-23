import unicodedata

from flask import current_app


REPORTABLE_PRODUCT_STATUSES = frozenset({"active", "sold"})
EFFECTIVE_REPORT_STATUSES = frozenset({"pending", "confirmed"})


class ReportReasonError(ValueError):
    pass


def normalize_report_reason(value: object) -> str:
    if not isinstance(value, str):
        raise ReportReasonError("신고 사유를 입력하세요.")

    normalized = unicodedata.normalize(
        "NFC", value.replace("\r\n", "\n").replace("\r", "\n")
    ).strip()
    min_chars = current_app.config["REPORT_REASON_MIN_CHARS"]
    max_chars = current_app.config["REPORT_REASON_MAX_CHARS"]
    max_bytes = current_app.config["REPORT_REASON_MAX_BYTES"]
    if not min_chars <= len(normalized) <= max_chars:
        raise ReportReasonError(
            f"신고 사유는 {min_chars}자 이상 {max_chars}자 이하이어야 합니다."
        )
    if len(normalized.encode("utf-8")) > max_bytes:
        raise ReportReasonError("신고 사유의 바이트 길이가 너무 깁니다.")
    for character in normalized:
        code_point = ord(character)
        if code_point == 0x7F or (code_point < 0x20 and character not in "\t\n"):
            raise ReportReasonError("신고 사유에 허용되지 않는 문자가 있습니다.")
    return normalized
