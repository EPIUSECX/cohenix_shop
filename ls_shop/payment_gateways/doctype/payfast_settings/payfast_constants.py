# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
Constants for PayFast payment gateway integration.
Reference: https://developers.payfast.co.za/docs
"""

# Payment statuses returned by PayFast
PAYMENT_STATUS_COMPLETE = "COMPLETE"
PAYMENT_STATUS_FAILED = "FAILED"
PAYMENT_STATUS_CANCELLED = "CANCELLED"

VALID_PAYMENT_STATUSES = [
    PAYMENT_STATUS_COMPLETE,
    PAYMENT_STATUS_FAILED,
    PAYMENT_STATUS_CANCELLED,
]

# Order statuses in PayFast Order doctype
ORDER_STATUS_PENDING = "Pending"
ORDER_STATUS_COMPLETE = "Complete"
ORDER_STATUS_FAILED = "Failed"
ORDER_STATUS_CANCELLED = "Cancelled"

# PayFast server IP range for ITN validation
# Source: https://developers.payfast.co.za/docs#notify_page
PAYFAST_IP_ADDRESSES = [
    "197.97.145.144",
    "197.97.145.145",
    "197.97.145.146",
    "197.97.145.147",
    "197.97.145.148",
    "197.97.145.149",
    "197.97.145.150",
    "197.97.145.151",
    "197.97.145.152",
    "197.97.145.153",
    "197.97.145.154",
    "197.97.145.155",
    "197.97.145.156",
    "197.97.145.157",
    "197.97.145.158",
    "197.97.145.159",
]

# PayFast API URLs
PAYFAST_SANDBOX_URL = "https://sandbox.payfast.co.za/eng/process"
PAYFAST_LIVE_URL = "https://www.payfast.co.za/eng/process"
PAYFAST_VALIDATION_URL = "https://www.payfast.co.za/eng/query/validate"
PAYFAST_SANDBOX_VALIDATION_URL = "https://sandbox.payfast.co.za/eng/query/validate"

# Supported currency
SUPPORTED_CURRENCY = "ZAR"

# Minimum transaction amount in ZAR
MINIMUM_TRANSACTION_AMOUNT = 5.00

# Required ITN fields
REQUIRED_ITN_FIELDS = ["m_payment_id", "payment_status", "amount_gross", "signature"]

# Optional but recommended ITN fields
OPTIONAL_ITN_FIELDS = [
    "pf_payment_id",
    "merchant_id",
    "amount_fee",
    "amount_net",
    "name_first",
    "name_last",
    "email_address",
    "payment_method",
    "item_name",
    "item_description",
]

