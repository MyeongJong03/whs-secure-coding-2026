TITLE_MIN_LENGTH = 1
TITLE_MAX_LENGTH = 100
DESCRIPTION_MIN_LENGTH = 1
DESCRIPTION_MAX_LENGTH = 2000
PRICE_MIN = 1
PRICE_MAX = 1_000_000_000
SEARCH_QUERY_MAX_LENGTH = 100
SEARCH_PAGE_MIN = 1
SEARCH_PAGE_MAX = 1000
PRODUCTS_PER_PAGE = 20

PUBLIC_STATUSES = ("active", "sold")
OWNER_EDITABLE_STATUSES = frozenset(PUBLIC_STATUSES)
ALL_PRODUCT_STATUSES = ("active", "sold", "hidden", "deleted")
CREATED_STATUS = "active"

SEARCH_STATUSES = ("all", "active", "sold")
SEARCH_SORTS = ("newest", "oldest", "price_low", "price_high", "title")

ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
FORMAT_MIMETYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
