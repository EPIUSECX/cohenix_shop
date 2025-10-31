# Copyright (c) 2025, ls_shop and contributors
# For license information, please see license.txt

"""
PayFast ITN (Instant Transaction Notification) handler.
"""

import json

import frappe
from frappe import _

from ls_shop.payment_gateways.doctype.payfast_settings.payfast_utils import (
    confirm_payment_with_payfast,
    verify_itn_signature,
)
from ls_shop.payment_gateways.doctype.payfast_settings.payfast_constants import (
    REQUIRED_ITN_FIELDS,
    VALID_PAYMENT_STATUSES,
    PAYMENT_STATUS_COMPLETE,
)


@frappe.whitelist(allow_guest=True)
def handle_itn():
    """
    ERPNext-compliant ITN handler for PayFast.
    
    Returns:
        dict: Response with status message
    """
    try:
        # Get ITN data from form
        itn_data = dict(frappe.request.form)
        
        # Log ITN received
        frappe.log_error(
            f"PayFast ITN received: {json.dumps(itn_data, indent=2)}",
            "PayFast ITN Received"
        )
        
        # Validate ITN data structure
        if not validate_itn_data(itn_data):
            frappe.log_error(
                f"PayFast ITN validation failed: {json.dumps(itn_data, indent=2)}",
                "PayFast ITN Validation Error"
            )
            frappe.response.http_status_code = 400
            frappe.response["message"] = "Invalid ITN data"
            return
        
        # Process ITN
        process_itn_notification(itn_data)
        
        frappe.response["message"] = "OK"

    except Exception as e:
        error_msg = f"Error processing PayFast ITN: {str(e)}"
        frappe.log_error(
            f"{error_msg}\n{frappe.get_traceback()}\nITN Data: {json.dumps(dict(frappe.request.form), indent=2)}",
            "PayFast ITN Processing Error"
        )
        frappe.response.http_status_code = 500
        frappe.response["message"] = "Error processing ITN"


def process_itn_notification(itn_data: dict):
    """
    Process ITN notification.
    
    Args:
        itn_data: Dictionary containing ITN data from PayFast
    """
    try:
        # Get PayFast settings from custom_str1
        settings_name = itn_data.get("custom_str1")
        if not settings_name:
            frappe.log_error(
                "PayFast ITN missing custom_str1 (settings reference)",
                "PayFast ITN Processing Error"
            )
            return False
            
        settings = frappe.get_doc("Payfast Settings", settings_name)
        
        # CRITICAL SECURITY: Confirm payment with PayFast
        confirmation_result = confirm_payment_with_payfast(itn_data, settings.sandbox_mode)
        
        if not confirmation_result:
            frappe.log_error(
                f"PayFast payment confirmation failed for settings {settings_name}",
                "PayFast Payment Confirmation Failed"
            )
            return False
        
        # Find PayFast Payment Request by m_payment_id
        m_payment_id = itn_data.get("m_payment_id")
        if not m_payment_id:
            frappe.log_error(
                "PayFast ITN missing m_payment_id",
                "PayFast ITN Processing Error"
            )
            return False
        
        payment_request = frappe.db.get_value("Payfast Payment Request", {"m_payment_id": m_payment_id})
        
        if not payment_request:
            frappe.log_error(
                f"Payfast Payment Request not found for m_payment_id: {m_payment_id}",
                "PayFast ITN Processing Error"
            )
            return False
        
        # Verify signature
        passphrase = settings.get_password("passphrase", raise_exception=False)
        signature_valid = verify_itn_signature(itn_data, passphrase)
        
        if not signature_valid:
            frappe.log_error(
                f"PayFast ITN signature verification failed for m_payment_id: {m_payment_id}",
                "PayFast ITN Signature Verification Failed"
            )
            return False
        
        # Update payment request
        pr_doc = frappe.get_doc("Payfast Payment Request", payment_request)
        payment_status = itn_data.get("payment_status")
        
        if payment_status == PAYMENT_STATUS_COMPLETE:
            pr_doc.status = "Complete"
            pr_doc.pf_payment_id = itn_data.get("pf_payment_id")
            pr_doc.payment_method = itn_data.get("payment_method")
            pr_doc.save(ignore_permissions=True)
            
            # Trigger order creation
            if pr_doc.ref_doctype == "Quotation" and pr_doc.ref_docname:
                from ls_shop.api.payments import submit_quotation_and_create_order, PaymentMode
                submit_quotation_and_create_order(
                    pr_doc.ref_docname,
                    PaymentMode.PAYFAST,
                    itn_data.get("pf_payment_id") or m_payment_id
                )
        elif payment_status in ["FAILED", "CANCELLED"]:
            pr_doc.status = "Failed" if payment_status == "FAILED" else "Cancelled"
            pr_doc.save(ignore_permissions=True)
        
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Failed to process PayFast ITN notification: {str(e)}\n{frappe.get_traceback()}",
            "PayFast ITN Processing Error"
        )
        raise


def validate_itn_data(itn_data: dict) -> bool:
    """
    Validate PayFast ITN data structure and required fields.
    
    Args:
        itn_data: Dictionary containing ITN data from PayFast
        
    Returns:
        bool: True if data is valid, False otherwise
    """
    try:
        # Check required fields
        for field in REQUIRED_ITN_FIELDS:
            if not itn_data.get(field):
                frappe.log_error(
                    f"PayFast ITN missing required field: {field}",
                    "PayFast ITN Validation Error"
                )
                return False
        
        # Validate payment status
        payment_status = itn_data.get("payment_status")
        if payment_status not in VALID_PAYMENT_STATUSES:
            frappe.log_error(
                f"PayFast ITN invalid payment status: {payment_status}",
                "PayFast ITN Validation Error"
            )
            return False
        
        # Validate amount format
        try:
            amount = float(itn_data.get("amount_gross", 0))
            if amount <= 0:
                frappe.log_error(
                    f"PayFast ITN invalid amount: {amount}",
                    "PayFast ITN Validation Error"
                )
                return False
        except (ValueError, TypeError):
            frappe.log_error(
                f"PayFast ITN invalid amount_gross format: {itn_data.get('amount_gross')}",
                "PayFast ITN Validation Error"
            )
            return False
        
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error validating PayFast ITN data: {str(e)}\n{frappe.get_traceback()}",
            "PayFast ITN Validation Error"
        )
        return False

