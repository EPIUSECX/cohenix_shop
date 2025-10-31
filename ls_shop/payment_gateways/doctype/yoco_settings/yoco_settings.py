# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import hashlib
import hmac
import json
from urllib.parse import urlencode

import frappe
from frappe import _
# Removed create_request_log import - standalone implementation
from frappe.model.document import Document
from frappe.utils import call_hook_method, flt, get_url


def create_payment_gateway(gateway, settings=None, controller=None):
	# NOTE: we don't translate Payment Gateway name because it is an internal doctype
	if frappe.db.exists("Payment Gateway", gateway):
		payment_gateway = frappe.get_doc("Payment Gateway", gateway)
		payment_gateway.gateway_settings = settings
		payment_gateway.gateway_controller = controller
		payment_gateway.save(ignore_permissions=True)
	else:
		payment_gateway = frappe.get_doc(
			{
				"doctype": "Payment Gateway",
				"gateway": gateway,
				"gateway_settings": settings,
				"gateway_controller": controller,
			}
		)
		payment_gateway.insert(ignore_permissions=True)


class YocoSettings(Document):
	supported_currencies = ("ZAR",)

	def on_update(self):
		"""ERPNext compliant payment gateway registration"""
		create_payment_gateway(
			"Yoco-" + self.name,
			settings="Yoco Settings",
			controller=self.name,
		)
		call_hook_method("payment_gateway_enabled", gateway="Yoco-" + self.name)

	def validate(self):
		"""Validate Yoco settings"""
		if not self.flags.ignore_mandatory:
			self.validate_yoco_credentials()

	def validate_yoco_credentials(self):
		"""Validate Yoco API credentials"""
		if self.public_key and self.get_password("secret_key", raise_exception=False):
			try:
				# Test API credentials with a simple API call
				self.test_connection()
			except Exception:
				frappe.throw(_("Invalid Yoco API credentials. Please check your API keys."))

	@frappe.whitelist()
	def test_connection(self):
		"""Test the connection to the Yoco API."""
		import requests

		secret_key = self.get_password(fieldname="secret_key", raise_exception=False)
		if not secret_key:
			return {"status": "error", "message": "Please set the Secret Key."}

		# Use the correct Yoco API endpoint for testing credentials
		test_url = "https://payments.yoco.com/api/webhooks"

		headers = {
			"Authorization": f"Bearer {secret_key}",
			"Content-Type": "application/json"
		}

		try:
			response = requests.get(test_url, headers=headers, timeout=10)
			response.raise_for_status()

			return {"status": "success", "message": "Connection successful!"}

		except requests.exceptions.RequestException as e:
			return {"status": "error", "message": f"Connection failed: {e}"}
		except Exception as e:
			return {"status": "error", "message": f"An unexpected error occurred: {e}"}

	def validate_transaction_currency(self, currency):
		"""Validate currency is supported"""
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. Yoco does not support transactions in currency '{0}'"
				).format(currency)
			)

	def validate_minimum_transaction_amount(self, currency, amount):
		"""Validate minimum transaction amount"""
		# Minimum transaction amount is R1.00 (100 cents)
		minimum_amount = 1.00

		if flt(amount) < minimum_amount:
			frappe.throw(
				_("For currency {0}, the minimum transaction amount should be {1}").format(
					currency, minimum_amount
				)
			)

	def get_payment_url(self, **kwargs):
		"""Get payment URL - standalone implementation"""
		# Not used in ls_shop - payment URLs are generated in Payment Request
		pass

	def create_yoco_order(self, amount, currency="ZAR", internal_reference_id=None, customer_details=None):
		"""Create Yoco order and return order data for Payment Request"""
		import requests
		import uuid
		
		secret_key = self.get_password("secret_key", raise_exception=False)
		if not secret_key:
			frappe.throw(_("Yoco Secret Key not configured"))
		
		# Generate unique order ID
		order_id = f"yoco_order_{uuid.uuid4().hex[:16]}"
		
		# Create checkout session via Yoco API
		api_url = "https://payments.yoco.com/api/v1/checkouts"
		
		payload = {
			"amount": int(amount * 100),  # Convert to cents
			"currency": currency,
			"metadata": {
				"order_id": order_id,
				"internal_reference": internal_reference_id or str(order_id)
			}
		}
		
		if customer_details:
			payload.update({
				"customer": {
					"email": customer_details.get("email"),
					"phone": customer_details.get("phone"),
				}
			})
		
		headers = {
			"Authorization": f"Bearer {secret_key}",
			"Content-Type": "application/json"
		}
		
		try:
			response = requests.post(api_url, json=payload, headers=headers, timeout=30)
			response.raise_for_status()
			order_data = response.json()
			
			# Yoco checkout response structure
			checkout_id = order_data.get("id") or order_data.get("checkout_id")
			checkout_url = order_data.get("url") or order_data.get("checkout_url") or order_data.get("redirect_url")
			
			return {
				"order_id": order_id,
				"yoco_charge_id": checkout_id,
				"yoco_order_url": checkout_url,
				"status": order_data.get("status", "Pending")
			}
		except requests.exceptions.RequestException as e:
			frappe.log_error(
				f"Yoco order creation failed: {str(e)}\nResponse: {response.text if 'response' in locals() else 'No response'}",
				"Yoco Order Creation Error"
			)
			frappe.throw(_("Failed to create Yoco order: {0}").format(str(e)))

	def verify_webhook_signature(self, payload, signature, secret):
		"""Verify the signature of the incoming webhook."""
		if not signature or not secret:
			return False
		
		generated_signature = hmac.new(
			secret.encode('utf-8'),
			payload,
			hashlib.sha256
		).hexdigest()
		
		return hmac.compare_digest(generated_signature, signature)

