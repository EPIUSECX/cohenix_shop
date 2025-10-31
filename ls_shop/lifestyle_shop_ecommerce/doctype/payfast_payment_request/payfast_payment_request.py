# Copyright (c) 2025, ls_shop and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class PayfastPaymentRequest(Document):
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
		m_payment_id: DF.Data | None
		name: DF.Int | None
		payfast_order_url: DF.Data | None
		payfast_payment_id: DF.Data | None
		payment_method: DF.Data | None
		pf_payment_id: DF.Data | None
		ref_docname: DF.DynamicLink | None
		ref_doctype: DF.Link | None
		status: DF.Literal[
			"Pending",
			"Complete",
			"Cancelled",
			"Failed",
		]
	# end: auto-generated types

	def before_save(self):
		# m_payment_id will be set after insert when name is generated
		pass
	
	def after_insert(self):
		# Set m_payment_id after insert when name is available
		if not self.m_payment_id:
			self.m_payment_id = str(self.name)
			self.db_set("m_payment_id", self.m_payment_id, update_modified=False)

	@frappe.whitelist()
	def get_payment_form(self):
		"""Get Payfast payment form data for redirect"""
		# Ensure m_payment_id is set
		if not self.m_payment_id:
			self.m_payment_id = str(self.name)
			self.db_set("m_payment_id", self.m_payment_id, update_modified=False)
		
		payfast_settings = self.get_payfast_settings()
		base_url = get_url("").rstrip("/")
		
		payment_form = payfast_settings.generate_payment_form(self, base_url)
		
		return payment_form

	def get_payfast_settings(self):
		"""Get Payfast Settings document"""
		settings_list = frappe.get_all("Payfast Settings", limit=1)
		if not settings_list:
			frappe.throw(frappe._("Payfast Settings not found. Please configure Payfast payment gateway."))
		return frappe.get_doc("Payfast Settings", settings_list[0].name)

	@frappe.whitelist()
	def sync_status(self):
		"""Sync payment status from Payfast ITN data"""
		# This will typically be called from ITN handler
		# For manual sync, would need to query Payfast API
		# For now, status is updated via ITN webhook
		pass

