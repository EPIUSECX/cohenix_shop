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
		
		import requests
		yoco_settings = self.get_yoco_settings()
		secret_key = yoco_settings.get_password("secret_key", raise_exception=False)
		
		if not secret_key:
			frappe.throw(frappe._("Yoco Secret Key not configured"))
		
		api_url = f"https://payments.yoco.com/api/v1/charges/{self.yoco_charge_id}"
		
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
			frappe.log_error(
				f"Yoco status sync failed: {str(e)}",
				"Yoco Status Sync Error"
			)
			frappe.throw(frappe._("Failed to sync status from Yoco: {0}").format(str(e)))

	@frappe.whitelist()
	def process_yoco_payment(self, yoco_token):
		"""Process Yoco payment token from inline SDK - create charge via API"""
		import requests
		
		yoco_settings = self.get_yoco_settings()
		secret_key = yoco_settings.get_password("secret_key", raise_exception=False)
		
		if not secret_key:
			frappe.throw(frappe._("Yoco Secret Key not configured"))
		
		# Charge the payment using the token from Yoco SDK
		# Yoco API: POST /api/v1/charges with token
		api_url = "https://payments.yoco.com/api/v1/charges"
		
		payload = {
			"amount": int(float(self.amount) * 100),  # Convert to cents
			"currency": self.currency_code or "ZAR",
			"token": yoco_token,
			"metadata": {
				"payment_request": self.name,
				"reference_doctype": self.ref_doctype,
				"reference_docname": self.ref_docname
			}
		}
		
		headers = {
			"Authorization": f"Bearer {secret_key}",
			"Content-Type": "application/json"
		}
		
		try:
			response = requests.post(api_url, json=payload, headers=headers, timeout=30)
			response.raise_for_status()
			charge_data = response.json()
			
			# Update payment request with charge details
			self.yoco_charge_id = charge_data.get("id")
			charge_status = charge_data.get("status", "").lower()
			if charge_status == "succeeded":
				self.status = "Paid"
			elif charge_status == "failed":
				self.status = "Failed"
			else:
				self.status = "Pending"
			
			self.payment_method = charge_data.get("source", {}).get("type")
			self.save()
			
			# Process payment confirmation if successful
			if self.status == "Paid":
				from ls_shop.api.payments import confirm_payment
				confirm_payment(payment_request_doctype="Yoco Payment Request", payment_request_name=self.name)
				
				# Return redirect URL
				quotation = frappe.get_doc(self.ref_doctype, self.ref_docname)
				return {
					"redirect_to": f"/{frappe.local.lang}/account/orders/confirmation?payment_request={self.name}&quotation={quotation.name}",
					"status": "success"
				}
			else:
				return {
					"redirect_to": f"/payment-failed?payment_request={self.name}",
					"status": "failed"
				}
			
		except requests.exceptions.RequestException as e:
			error_response = response.text if 'response' in locals() else 'No response'
			frappe.log_error(
				f"Yoco payment processing failed: {str(e)}\nResponse: {error_response}",
				"Yoco Payment Processing Error"
			)
			frappe.throw(frappe._("Failed to process Yoco payment: {0}").format(str(e)))

