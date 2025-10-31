# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
PayFast Settings DocType for managing PayFast payment gateway configuration.
"""

import json

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method, flt, get_url

from .payfast_constants import (
    SUPPORTED_CURRENCY,
    MINIMUM_TRANSACTION_AMOUNT,
    PAYFAST_SANDBOX_URL,
    PAYFAST_LIVE_URL,
)
from .payfast_utils import generate_payment_signature


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


class PayfastSettings(Document):
	"""PayFast Settings DocType for payment gateway configuration."""
	
	supported_currencies = (SUPPORTED_CURRENCY,)

	def on_update(self):
		"""
		Called after document save.
		
		Registers payment gateway with ERPNext and enables it.
		"""
		create_payment_gateway(
			"Payfast-" + self.name,
			settings="Payfast Settings",
			controller=self.name,
		)
		call_hook_method("payment_gateway_enabled", gateway="Payfast-" + self.name)

	def validate(self):
		"""
		Validate PayFast settings before save.
		
		Ensures all required credentials are configured.
		"""
		if not self.flags.ignore_mandatory:
			self.validate_payfast_credentials()
			self.validate_urls()

	def validate_payfast_credentials(self):
		"""
		Validate PayFast merchant credentials.
		
		Raises:
			frappe.ValidationError: If required credentials are missing
		"""
		if not self.merchant_id:
			frappe.throw(_("Merchant ID is required"))
		if not self.merchant_key:
			frappe.throw(_("Merchant Key is required"))

	def validate_urls(self):
		"""
		Validate configured URLs are accessible.
		
		Logs warnings if URLs appear invalid but doesn't block save.
		"""
		if self.notify_url:
			if not self.notify_url.startswith(('http://', 'https://')):
				frappe.msgprint(
					_("Notify URL should start with http:// or https://"),
					indicator="orange",
					alert=True
				)

	def validate_transaction_currency(self, currency):
		"""
		Validate that transaction currency is supported by PayFast.
		
		Args:
			currency: Currency code (e.g., "ZAR")
			
		Raises:
			frappe.ValidationError: If currency not supported
		"""
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. PayFast does not support transactions in currency '{0}'"
				).format(currency)
			)

	def validate_minimum_transaction_amount(self, currency, amount):
		"""
		Validate transaction amount meets PayFast minimum requirements.
		
		Args:
			currency: Transaction currency
			amount: Transaction amount
			
		Raises:
			frappe.ValidationError: If amount below minimum
		"""
		if flt(amount) < MINIMUM_TRANSACTION_AMOUNT:
			frappe.throw(
				_("For currency {0}, the minimum transaction amount should be {1}").format(
					currency, MINIMUM_TRANSACTION_AMOUNT
				)
			)

	def generate_payment_form(self, payment_request_doc, base_url=None):
		"""
		Generate PayFast payment form data for POST redirect.
		
		Args:
			payment_request_doc: Payfast Payment Request document
			base_url: Base URL for return/cancel/notify URLs
			
		Returns:
			dict: Contains payfast_url and form_data dict
		"""
		if base_url is None:
			base_url = get_url("").rstrip("/")
		
		# Build form_data in PayFast's required order
		form_data = {}
		
		# 1. Merchant details (required, first)
		form_data["merchant_id"] = self.merchant_id
		form_data["merchant_key"] = self.merchant_key
		
		# 2. Return/Cancel/Notify URLs
		if self.return_url:
			form_data["return_url"] = self.return_url
		else:
			# Use confirmation page with proper parameters for consistency
			form_data["return_url"] = f"{base_url}/account/orders/confirmation?payment_mode=payfast&reference_id={payment_request_doc.m_payment_id or payment_request_doc.name}&payment_request={payment_request_doc.name}"
		
		if self.cancel_url:
			form_data["cancel_url"] = self.cancel_url
		else:
			form_data["cancel_url"] = f"{base_url}/payment-failed"
		
		if self.notify_url:
			form_data["notify_url"] = self.notify_url
		else:
			form_data["notify_url"] = f"{base_url}/api/method/ls_shop.payment_gateways.payfast_itn.handle_itn"
		
		# 3. Buyer details
		if payment_request_doc.customer_email:
			form_data["email_address"] = payment_request_doc.customer_email
		
		if payment_request_doc.customer_forenames:
			form_data["name_first"] = payment_request_doc.customer_forenames
		if payment_request_doc.customer_surname:
			form_data["name_last"] = payment_request_doc.customer_surname
		
		# 4. Transaction details
		form_data["m_payment_id"] = payment_request_doc.name
		form_data["amount"] = "{:.2f}".format(flt(payment_request_doc.amount))
		form_data["item_name"] = f"Payment for {payment_request_doc.ref_docname}"
		
		# 5. Custom fields
		form_data["custom_str1"] = self.name  # PayFast Settings document name
		form_data["custom_str2"] = payment_request_doc.ref_docname if payment_request_doc.ref_docname else ""
		
		# Remove any empty values
		form_data = {k: v for k, v in form_data.items() if v}
		
		# Create signature
		passphrase = self.get_password("passphrase", raise_exception=False)
		form_data["signature"] = generate_payment_signature(form_data, passphrase)
		
		# Generate PayFast URL
		payfast_url = PAYFAST_SANDBOX_URL if self.sandbox_mode else PAYFAST_LIVE_URL
		
		return {
			"payfast_url": payfast_url,
			"form_data": form_data
		}

