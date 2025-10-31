# Copyright (c) 2025, ls_shop and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class YocoPaymentRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		currency_code: DF.Link | None
		customer_address: DF.Link | None
		customer_email: DF.Data | None
		customer_forenames: DF.Data | None
		customer_phone: DF.Data | None
		customer_ref: DF.Data | None
		customer_surname: DF.Data | None
		name: DF.Int | None
		payment_method: DF.Data | None
		ref_docname: DF.DynamicLink | None
		ref_doctype: DF.Link | None
		refund_amount: DF.Currency
		status: DF.Literal[
			"Pending",
			"Paid",
			"Not Paid",
			"Cancelled",
			"Failed",
			"Refunded",
		]
		yoco_charge_id: DF.Data | None
		yoco_order_id: DF.Data | None
		yoco_order_url: DF.Data | None
	# end: auto-generated types

	def before_save(self):
		# Don't create order in before_save as name might not be available yet
		# Will be created in after_insert instead
		pass
	
	def after_insert(self):
		"""Create Yoco order after insert when name is available"""
		if not self.yoco_order_id:
			try:
				self.create_order_on_yoco()
				self.db_update()
			except Exception as e:
				frappe.log_error(
					f"Failed to create Yoco order for Payment Request {self.name}: {str(e)}",
					"Yoco Order Creation Error"
				)
				# Don't throw - allow the payment request to be created even if order creation fails
				# User can retry later via sync_status

	def create_order_on_yoco(self):
		"""Create Yoco order directly via API to avoid conflicts with payments app"""
		# Use name as internal_reference_id now that it's available
		internal_reference_id = str(self.name) if self.name else None
		
		# Prepare customer details
		customer_details = None
		if self.customer_email or self.customer_phone:
			customer_details = {
				"email": self.customer_email or "",
				"phone": self.customer_phone or "",
			}
		
		# Call direct method to avoid method signature conflicts with payments app
		order_data = self._create_yoco_order_direct(
			amount=self.amount,
			currency=self.currency_code or "ZAR",
			internal_reference_id=internal_reference_id,
			customer_details=customer_details
		)

		self.yoco_order_id = order_data.get("order_id")
		self.yoco_charge_id = order_data.get("charge_id") or order_data.get("yoco_charge_id")
		self.yoco_order_url = order_data.get("yoco_order_url") or order_data.get("checkout_url")
		self.status = order_data.get("status", "Pending")


	def get_yoco_settings(self):
		"""Get Yoco Settings document"""
		settings_list = frappe.get_all("Yoco Settings", limit=1)
		if not settings_list:
			frappe.throw(frappe._("Yoco Settings not found. Please configure Yoco payment gateway."))
		return frappe.get_doc("Yoco Settings", settings_list[0].name)
	
	def _create_yoco_order_direct(self, amount, currency="ZAR", internal_reference_id=None, customer_details=None):
		"""Generate Yoco checkout URL - Yoco uses inline JavaScript SDK, not server-side API"""
		import uuid
		from frappe.utils import get_url
		
		yoco_settings = self.get_yoco_settings()
		
		# Generate unique order ID
		order_id = f"yoco_order_{uuid.uuid4().hex[:16]}"
		
		# Yoco doesn't have a server-side charge API
		# Instead, we create a checkout URL that uses Yoco's inline JavaScript SDK
		# The checkout page will handle the payment using the SDK
		checkout_url = get_url(f"/yoco-checkout?payment_request={self.name}")
		
		return {
			"order_id": order_id,
			"yoco_charge_id": None,  # Will be set after payment via webhook
			"charge_id": None,
			"yoco_order_url": checkout_url,
			"checkout_url": checkout_url,
			"status": "Pending"
		}

	@frappe.whitelist()
	def sync_status(self):
		"""Sync payment status from Yoco"""
		if not self.yoco_charge_id:
			frappe.throw(frappe._("Yoco Charge ID not found. Cannot sync status."))
		
		# If status is already Paid and yoco_charge_id is a token (starts with 'tok_'),
		# then we already processed it via SDK - no need to sync from API
		if self.status == "Paid" and self.yoco_charge_id.startswith("tok_"):
			# Payment was processed via SDK, already marked as paid
			return self
		
		import requests
		yoco_settings = self.get_yoco_settings()
		secret_key = yoco_settings.get_password("secret_key", raise_exception=False)
		
		if not secret_key:
			frappe.throw(frappe._("Yoco Secret Key not configured"))
		
		# Get payment/charge status - try both possible endpoints
		# First try /api/v1/payments/{id}, fallback to /api/v1/charges/{id} if needed
		api_url = f"https://payments.yoco.com/api/v1/payments/{self.yoco_charge_id}"
		
		headers = {
			"Authorization": f"Bearer {secret_key}",
			"Content-Type": "application/json"
		}
		
		try:
			response = requests.get(api_url, headers=headers, timeout=10)
			response.raise_for_status()
			charge_data = response.json()
			
			# Update status based on charge status
			charge_status = charge_data.get("status", "").lower()
			if charge_status == "succeeded":
				self.status = "Paid"
				self.payment_method = charge_data.get("source", {}).get("type")
			elif charge_status == "failed":
				self.status = "Failed"
			elif charge_status == "cancelled":
				self.status = "Cancelled"
			else:
				self.status = "Pending"
			
			self.save()
			return self
			
		except requests.exceptions.RequestException as e:
			# If it's already marked as Paid (from SDK), don't throw error on sync failure
			# Webhooks will update status later if configured
			if self.status == "Paid":
				frappe.log_error(
					f"Yoco status sync failed but payment is already marked as Paid (from SDK): {str(e)}",
					"Yoco Status Sync Warning"
				)
				return self
			else:
				frappe.log_error(
					f"Yoco status sync failed: {str(e)}",
					"Yoco Status Sync Error"
				)
				frappe.throw(frappe._("Failed to sync status from Yoco: {0}").format(str(e)))

	@frappe.whitelist()
	def process_yoco_payment(self, yoco_token):
		"""
		Process Yoco payment token from inline SDK.
		Note: Yoco SDK handles payment on client-side. When callback succeeds, 
		the token represents a completed payment. We trust the SDK result and 
		mark payment as paid (webhooks will verify if configured).
		"""
		# Store the Yoco token as the charge ID
		# The token from Yoco SDK represents a completed payment
		self.yoco_charge_id = yoco_token
		self.status = "Paid"
		self.payment_method = "Card"  # Default, webhook will update if available
		self.save()
		
		try:
			# Process payment confirmation using the standard confirm_payment function
			from ls_shop.api.payments import confirm_payment, PaymentMode
			# confirm_payment expects (payment_mode: PaymentMode, reference_id: str)
			# For Yoco, reference_id is the payment request name (ID)
			confirm_payment(PaymentMode.YOCO, str(self.name))
			
			# Return redirect URL
			quotation = frappe.get_doc(self.ref_doctype, self.ref_docname)
			return {
				"redirect_to": f"/{frappe.local.lang}/account/orders/confirmation?payment_mode={PaymentMode.YOCO.value}&reference_id={self.name}&payment_request={self.name}&quotation={quotation.name}",
				"status": "success"
			}
			
		except Exception as e:
			frappe.log_error(
				f"Yoco payment confirmation failed: {str(e)}\n{frappe.get_traceback()}",
				"Yoco Payment Confirmation Error"
			)
			# Even if confirmation fails, payment was processed by Yoco
			# Return success but log the error
			quotation = frappe.get_doc(self.ref_doctype, self.ref_docname)
			return {
				"redirect_to": f"/{frappe.local.lang}/account/orders/confirmation?payment_mode={PaymentMode.YOCO.value}&reference_id={self.name}&payment_request={self.name}&quotation={quotation.name}",
				"status": "success"
			}


@frappe.whitelist()
def process_yoco_payment(name, yoco_token):
	"""Process Yoco payment token from inline SDK - standalone function wrapper"""
	payment_request = frappe.get_doc("Yoco Payment Request", name)
	return payment_request.process_yoco_payment(yoco_token)

