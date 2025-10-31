# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
Utility functions for PayFast payment gateway integration.
Consolidates common functionality used across multiple modules.
"""

import hashlib
import requests
from urllib.parse import urlencode

import frappe
from frappe import _

from .payfast_constants import (
    PAYFAST_IP_ADDRESSES,
    PAYFAST_VALIDATION_URL,
    PAYFAST_SANDBOX_VALIDATION_URL,
)


def verify_itn_signature(itn_data: dict, passphrase: str = None) -> bool:
    """
    Verify PayFast ITN signature using MD5 hash.
    
    This implementation matches the payment signature generation method
    to ensure consistency.
    
    Args:
        itn_data: Dictionary containing ITN data from PayFast
        passphrase: Optional passphrase for enhanced security
        
    Returns:
        bool: True if signature is valid, False otherwise
        
    Reference:
        https://developers.payfast.co.za/docs#security
    """
    try:
        # Extract signature from data
        received_signature = itn_data.get("signature")
        if not received_signature:
            frappe.log_error(
                "PayFast ITN missing signature field",
                "PayFast Signature Verification Error"
            )
            return False
        
        # Create data string for signature verification (excluding signature field)
        verification_data = {k: v for k, v in itn_data.items() if k != "signature"}
        
        # CRITICAL: Use insertion order NOT alphabetical (per PayFast docs)
        # PayFast explicitly states: "Do not use the API signature format, which uses alphabetical ordering!"
        data_string = urlencode(list(verification_data.items()))
        
        # Add passphrase if configured (not URL encoded)
        if passphrase:
            data_string += f"&passphrase={passphrase}"
        
        # Generate signature using MD5
        expected_signature = hashlib.md5(data_string.encode("utf-8")).hexdigest()
        
        # Compare signatures
        is_valid = expected_signature == received_signature
        
        if not is_valid:
            frappe.log_error(
                f"PayFast ITN signature verification failed\n"
                f"Expected: {expected_signature}\n"
                f"Received: {received_signature}\n"
                f"Data string: {data_string}",
                "PayFast Signature Verification Failed"
            )
        else:
            frappe.log_error(
                f"PayFast ITN signature verified successfully: {received_signature}",
                "PayFast Signature Verification Success"
            )
        
        return is_valid
        
    except Exception as e:
        frappe.log_error(
            f"Error verifying PayFast ITN signature: {str(e)}\n{frappe.get_traceback()}",
            "PayFast Signature Verification Error"
        )
        return False


def validate_itn_source_ip(source_ip: str = None) -> bool:
    """
    Validate that ITN request comes from PayFast servers.
    
    Args:
        source_ip: Source IP address. If None, uses frappe.request.remote_addr
        
    Returns:
        bool: True if IP is from PayFast, False otherwise
        
    Reference:
        https://developers.payfast.co.za/docs#notify_page
        PayFast IP range: 197.97.145.144/28
    """
    try:
        if source_ip is None:
            source_ip = frappe.request.headers.get('X-Forwarded-For', frappe.request.remote_addr)
            # If X-Forwarded-For has multiple IPs, get the first one
            if ',' in source_ip:
                source_ip = source_ip.split(',')[0].strip()
        
        # Validate source IP is from PayFast
        if source_ip not in PAYFAST_IP_ADDRESSES:
            frappe.log_error(
                f"PayFast ITN received from unauthorized IP: {source_ip}\nAllowed IPs: {', '.join(PAYFAST_IP_ADDRESSES)}",
                "PayFast IP Validation Failed"
            )
            return False
        
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error validating PayFast ITN source IP: {str(e)}\n{frappe.get_traceback()}",
            "PayFast IP Validation Error"
        )
        return False


def confirm_payment_with_payfast(itn_data: dict, sandbox_mode: bool = False) -> bool:
    """
    Confirm payment data with PayFast by POSTing back to their validation endpoint.
    This is a critical security step per PayFast documentation.
    
    Args:
        itn_data: ITN data received from PayFast
        sandbox_mode: Whether to use sandbox validation URL
        
    Returns:
        bool: True if PayFast confirms the payment, False otherwise
        
    Reference:
        https://developers.payfast.co.za/docs#step_4
    """
    try:
        # Select appropriate validation URL
        validation_url = PAYFAST_SANDBOX_VALIDATION_URL if sandbox_mode else PAYFAST_VALIDATION_URL
        
        # Prepare data for validation (exclude signature as PayFast will validate it)
        validation_data = {k: v for k, v in itn_data.items() if k != "signature"}
        
        # POST data back to PayFast for validation
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post(
            validation_url,
            data=urlencode(validation_data),
            headers=headers,
            timeout=10
        )
        
        # Check response
        if response.status_code == 200 and response.text.strip() == "VALID":
            return True
        else:
            frappe.log_error(
                f"PayFast payment confirmation failed\nStatus: {response.status_code}\nResponse: {response.text}\nData: {validation_data}",
                "PayFast Payment Confirmation Failed"
            )
            return False
            
    except requests.exceptions.Timeout:
        frappe.log_error(
            "PayFast payment confirmation timed out",
            "PayFast Payment Confirmation Timeout"
        )
        return False
    except Exception as e:
        frappe.log_error(
            f"Error confirming payment with PayFast: {str(e)}\n{frappe.get_traceback()}",
            "PayFast Payment Confirmation Error"
        )
        return False


def generate_payment_signature(form_data: dict, passphrase: str = None) -> str:
    """
    Generate MD5 signature for PayFast payment form.
    
    This implementation follows PayFast's official documentation and sample code
    to ensure signature compatibility.

    Args:
        form_data: Payment form data to sign
        passphrase: Optional passphrase for enhanced security

    Returns:
        str: MD5 hash signature

    Reference:
        https://developers.payfast.co.za/docs#security
    """
    # Create URL encoded string - exclude only the signature field
    # PayFast requires ALL other fields including custom_str1 and custom_str2
    signature_data = {k: v for k, v in form_data.items() if k != "signature"}
    
    # CRITICAL: Use insertion order NOT alphabetical ordering
    # PayFast explicitly states: "Do not use the API signature format, which uses alphabetical ordering!"
    # Fields must be in the order they were added to the dictionary
    pf_output = urlencode(list(signature_data.items()))

    # Add passphrase if provided (not URL encoded, as per PayFast docs)
    if passphrase:
        pf_output += f"&passphrase={passphrase}"

    # Generate MD5 hash
    signature = hashlib.md5(pf_output.encode("utf-8")).hexdigest()

    return signature


def get_payfast_settings(settings_name: str = None):
    """
    Get PayFast Settings document.
    
    Args:
        settings_name: Name of the PayFast Settings document. 
                      If None, tries to get the first/only settings document.
        
    Returns:
        PayfastSettings: The settings document
        
    Raises:
        frappe.DoesNotExistError: If settings document not found
    """
    if settings_name:
        return frappe.get_doc("Payfast Settings", settings_name)
    
    # Try to get the first settings document
    settings_list = frappe.get_all("Payfast Settings", limit=1)
    if settings_list:
        return frappe.get_doc("Payfast Settings", settings_list[0].name)
    
    frappe.throw(_("No PayFast Settings found. Please create one first."))

