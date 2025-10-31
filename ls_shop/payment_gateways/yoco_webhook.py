# Copyright (c) 2025, ls_shop and contributors
# For license information, please see license.txt

import hashlib
import hmac
import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def handle_webhook():
	"""
	ERPNext-compliant webhook handler for Yoco notifications.
	"""
	try:
		# Get webhook data
		request_body = frappe.request.get_data()
		yoco_signature = frappe.request.headers.get("X-Yoco-Signature")
		
		# Get Yoco settings
		settings_list = frappe.get_all("Yoco Settings", limit=1)
		if not settings_list:
			frappe.throw(_("Yoco Settings not found"), frappe.PermissionError)
		
		settings = frappe.get_doc("Yoco Settings", settings_list[0].name)
		webhook_secret = settings.get_password(fieldname="webhook_secret", raise_exception=False)

		# Verify webhook signature
		if not verify_signature(request_body, yoco_signature, webhook_secret):
			frappe.log_error(
				f"Yoco webhook signature verification failed. Signature: {yoco_signature}",
				"Yoco Webhook Signature Error"
			)
			frappe.throw(_("Invalid signature"), frappe.PermissionError)

		# Parse payload
		payload = json.loads(request_body)
		event_type = payload.get("type")
		
		# Log webhook received
		frappe.log_error(
			f"Yoco webhook received: {event_type}\nPayload: {json.dumps(payload, indent=2)}",
			"Yoco Webhook Received"
		)

		# Process webhook
		process_webhook_event(event_type, payload)
		
		frappe.response["message"] = "Webhook processed successfully"

	except json.JSONDecodeError as e:
		frappe.log_error(
			f"Yoco webhook payload is not valid JSON: {str(e)}\nPayload: {frappe.request.get_data()}",
			"Yoco Webhook JSON Error"
		)
		frappe.throw(_("Invalid JSON payload"), frappe.ValidationError)
		
	except Exception as e:
		frappe.log_error(
			f"Error processing Yoco webhook: {str(e)}\n{frappe.get_traceback()}",
			"Yoco Webhook Processing Error"
		)
		frappe.throw(_("Error processing webhook"), frappe.ValidationError)


def verify_signature(request_body, signature, secret):
	"""Verify the signature of the incoming webhook."""
	if not signature or not secret:
		return False
	
	generated_signature = hmac.new(
		secret.encode('utf-8'),
		request_body,
		hashlib.sha256
	).hexdigest()
	
	return hmac.compare_digest(generated_signature, signature)


def process_webhook_event(event_type: str, payload: dict):
	"""Process webhook event"""
	try:
		if event_type == "charge.succeeded":
			handle_charge_succeeded(payload)
		elif event_type == "charge.failed":
			handle_charge_failed(payload)
		else:
			frappe.log_error(
				f"Unhandled Yoco webhook event: {event_type}",
				"Yoco Webhook Unhandled Event"
			)
	except Exception as e:
		frappe.log_error(
			f"Failed to process Yoco webhook event {event_type}: {str(e)}\n{frappe.get_traceback()}",
			"Yoco Webhook Event Processing Error"
		)
		raise


def handle_charge_succeeded(payload: dict):
	"""Handle successful charge webhook"""
	charge_data = payload.get("data", {}).get("object", {})
	charge_id = charge_data.get("id")
	
	if not charge_id:
		frappe.log_error(
			"Yoco webhook missing charge ID",
			"Yoco Webhook Processing Error"
		)
		return
	
	# Find Yoco Payment Request by charge ID
	payment_request = frappe.db.get_value("Yoco Payment Request", {"yoco_charge_id": charge_id})
	
	if not payment_request:
		# Try to find by order_id in metadata
		metadata = charge_data.get("metadata", {})
		order_id = metadata.get("order_id")
		if order_id:
			payment_request = frappe.db.get_value("Yoco Payment Request", {"yoco_order_id": order_id})
	
	if not payment_request:
		frappe.log_error(
			f"Yoco Payment Request not found for charge_id: {charge_id}",
			"Yoco Webhook Processing Error"
		)
		return
	
	# Update payment request
	pr_doc = frappe.get_doc("Yoco Payment Request", payment_request)
	pr_doc.status = "Paid"
	pr_doc.yoco_charge_id = charge_id
	if charge_data.get("source"):
		pr_doc.payment_method = charge_data.get("source", {}).get("type")
	pr_doc.save(ignore_permissions=True)
	
	# Trigger order creation
	if pr_doc.ref_doctype == "Quotation" and pr_doc.ref_docname:
		from ls_shop.api.payments import submit_quotation_and_create_order, PaymentMode
		submit_quotation_and_create_order(
			pr_doc.ref_docname,
			PaymentMode.YOCO,
			charge_id or pr_doc.yoco_order_id
		)


def handle_charge_failed(payload: dict):
	"""Handle failed charge webhook"""
	charge_data = payload.get("data", {}).get("object", {})
	charge_id = charge_data.get("id")
	
	if not charge_id:
		return
	
	# Find and update payment request
	payment_request = frappe.db.get_value("Yoco Payment Request", {"yoco_charge_id": charge_id})
	if payment_request:
		pr_doc = frappe.get_doc("Yoco Payment Request", payment_request)
		pr_doc.status = "Failed"
		pr_doc.save(ignore_permissions=True)

