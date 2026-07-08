from enum import StrEnum


class NotificationKind(StrEnum):
    DUE_DATE = "due_date"
    EXPIRY = "expiry"
    POLICY_RENEWAL = "policy_renewal"
    WARRANTY_EXPIRY = "warranty_expiry"


class NotificationStatus(StrEnum):
    DISMISSED = "dismissed"
    PENDING = "pending"
    READ = "read"
