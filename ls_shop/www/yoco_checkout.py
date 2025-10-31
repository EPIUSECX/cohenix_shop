# Copyright (c) 2025, ls_shop and contributors
# For license information, please see license.txt

import frappe
from frappe import _


no_cache = True


def get_context(context):
	"""Prepare context for Yoco checkout page"""
	try:
		payment_request_name = frappe.local.request.args.get("payment_request")
		
		if not payment_request_name:
			frappe.throw(_("Payment request not found"), frappe.PermissionError)
		
		# Get payment request
		payment_request = frappe.get_doc("Yoco Payment Request", payment_request_name)
		
		# Verify user has access
		if frappe.session.user == "Guest":
			frappe.throw(_("Please login to complete payment"), frappe.PermissionError)
		
		# Get Yoco Settings
		yoco_settings = payment_request.get_yoco_settings()
		
		# Get public key
		public_key = yoco_settings.get("public_key")
		if not public_key:
			frappe.throw(_("Yoco Public Key not configured"), frappe.PermissionError)
		
		# Get quotation details
		quotation = frappe.get_doc(payment_request.ref_doctype, payment_request.ref_docname)
		
		# Ensure amount is set and is a valid number
		try:
			amount = float(payment_request.amount) if payment_request.amount else 0.0
		except (TypeError, ValueError):
			amount = 0.0
		
		if amount <= 0:
			frappe.throw(_("Invalid payment amount"), frappe.ValidationError)
		
		# Set all context variables
		context.payment_request = payment_request
		context.amount = amount
		context.currency = payment_request.currency_code or "ZAR"
		context.public_key = public_key
		context.reference_docname = quotation.name
		context.reference_doctype = quotation.doctype
		context.title = f"Payment for {quotation.name}"
		context.description = f"Payment for {quotation.doctype} {quotation.name}"
		context.payment_request_name = payment_request_name
		
		# Check if Apple Pay is enabled (if supported)
		context.enable_apple_pay = getattr(yoco_settings, "enable_apple_pay", False)
		context.apple_pay_merchant_id = getattr(yoco_settings, "apple_pay_merchant_id", "") or ""
		
	except Exception as e:
		# Log error
		frappe.log_error(
			f"Error in yoco-checkout context: {str(e)}\n{frappe.get_traceback()}",
			"Yoco Checkout Context Error"
		)
		# Re-raise the exception to show proper error page
		# Don't set default values here - let Frappe handle the error page
		raise

