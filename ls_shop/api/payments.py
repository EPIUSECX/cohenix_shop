from enum import StrEnum

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code
from erpnext.selling.doctype.quotation.quotation import _make_sales_order
from frappe.utils import getdate
from webshop.webshop.shopping_cart.cart import (
	_get_cart_quotation,
	get_cart_quotation,
)

from ls_shop.utils import get_cod_configuration


class PaymentMode(StrEnum):
	TELR = "telr"
	TABBY = "tabby"
	YOCO = "yoco"
	PAYFAST = "payfast"
	COD = "cod"


@frappe.whitelist()
def initiate_checkout_with_mode(payment_mode: PaymentMode):
	# Check if gateway is configured and enabled
	lifestyle_settings = frappe.get_cached_doc("Lifestyle Settings")
	
	if payment_mode == PaymentMode.YOCO:
		if not is_yoco_configured():
			frappe.throw(frappe._("Yoco payment gateway is not configured."))
		if not lifestyle_settings.get("yoco_enabled", 0):
			frappe.throw(frappe._("Yoco payment gateway is not enabled."))
	elif payment_mode == PaymentMode.PAYFAST:
		if not is_payfast_configured():
			frappe.throw(frappe._("Payfast payment gateway is not configured."))
		if not lifestyle_settings.get("payfast_enabled", 0):
			frappe.throw(frappe._("Payfast payment gateway is not enabled."))
	else:
		# For Telr/Tabby/COD, check Lifestyle Settings
		if payment_mode not in set(PaymentMode) or not lifestyle_settings.get(f"{payment_mode}_enabled"):
			frappe.throw(frappe._("Please select a valid payment mode."))

	quotation = _get_cart_quotation()
	update_delivery_charges(quotation)
	
	# Ensure quotation has rounded_total
	if not quotation.rounded_total:
		quotation.run_method("calculate_taxes_and_totals")
		quotation.save()
	
	# Get contact information - handle case where contact_person might be None
	customer_contact = None
	customer_phone = None
	
	if quotation.contact_person:
		customer_contact = frappe.db.get_value(
			"Contact",
			quotation.contact_person,
			["email_id", "first_name", "last_name"],
			as_dict=True,
		)
		
		customer_phone = frappe.db.get_value(
			"Contact Phone",
			{"parent": quotation.contact_person, "parenttype": "Contact", "idx": 1},
			"phone",
		)
	
	# Fallback to party (Customer) information if contact is missing
	if not customer_contact:
		# Try to get contact from customer/party
		if quotation.party_name:
			contacts = frappe.get_all(
				"Dynamic Link",
				filters={
					"link_doctype": "Customer",
					"link_name": quotation.party_name,
					"parenttype": "Contact",
				},
				fields=["parent"],
				limit=1,
			)
			if contacts:
				contact_name = contacts[0].parent
				customer_contact = frappe.db.get_value(
					"Contact",
					contact_name,
					["email_id", "first_name", "last_name"],
					as_dict=True,
				)
				customer_phone = frappe.db.get_value(
					"Contact Phone",
					{"parent": contact_name, "parenttype": "Contact", "idx": 1},
					"phone",
				)
	
	# Final fallback to user email if still no contact
	if not customer_contact:
		user_email = frappe.session.user
		if user_email and user_email != "Guest":
			customer_contact = {
				"email_id": frappe.db.get_value("User", user_email, "email"),
				"first_name": frappe.db.get_value("User", user_email, "first_name") or "",
				"last_name": frappe.db.get_value("User", user_email, "last_name") or "",
			}
	
	# Ensure customer_contact is a dict with required keys
	if not customer_contact:
		customer_contact = {
			"email_id": "",
			"first_name": "",
			"last_name": "",
		}
	payment_request = None
	if payment_mode == PaymentMode.TELR:
		payment_request = frappe.get_doc(
			{
				"doctype": "Telr Payment Request",
				"amount": quotation.rounded_total,
				"currency_code": "SAR" if frappe.conf.developer_mode else quotation.currency,
				"ref_doctype": quotation.doctype,
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name or "",
				"customer_phone": customer_phone or "",
				"customer_forenames": customer_contact.get("first_name") or "",
				"customer_surname": customer_contact.get("last_name") or "",
				"customer_email": customer_contact.get("email_id") or "",
				"customer_address": quotation.customer_address or "",
			}
		).insert()  # TODO: check for permissions with a normal user

	if payment_mode == PaymentMode.TABBY:
		payment_request = frappe.get_doc(
			{
				"doctype": "Tabby Payment Request",
				"amount": quotation.rounded_total,
				"currency_code": "SAR" if frappe.conf.developer_mode else quotation.currency,
				"ref_doctype": quotation.doctype,
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name or "",
				"customer_phone": customer_phone or "",
				"customer_name": quotation.customer_name or "",
				"customer_email": customer_contact.get("email_id") or "",
				"customer_address": quotation.customer_address or "",
			}
		).insert(ignore_permissions=True)

	if payment_mode == PaymentMode.YOCO:
		payment_request = frappe.get_doc(
			{
				"doctype": "Yoco Payment Request",
				"amount": quotation.rounded_total,
				"currency_code": "ZAR",  # Yoco only supports ZAR
				"ref_doctype": quotation.doctype,
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name or "",
				"customer_phone": customer_phone or "",
				"customer_forenames": customer_contact.get("first_name") or "",
				"customer_surname": customer_contact.get("last_name") or "",
				"customer_email": customer_contact.get("email_id") or "",
				"customer_address": quotation.customer_address or "",
			}
		)
		payment_request.flags.ignore_permissions = True
		payment_request.insert()

	if payment_mode == PaymentMode.PAYFAST:
		payment_request = frappe.get_doc(
			{
				"doctype": "Payfast Payment Request",
				"amount": quotation.rounded_total,
				"currency_code": "ZAR",  # Payfast only supports ZAR
				"ref_doctype": quotation.doctype,
				"ref_docname": quotation.name,
				"customer_ref": quotation.party_name or "",
				"customer_phone": customer_phone or "",
				"customer_forenames": customer_contact.get("first_name") or "",
				"customer_surname": customer_contact.get("last_name") or "",
				"customer_email": customer_contact.get("email_id") or "",
				"customer_address": quotation.customer_address or "",
			}
		)
		payment_request.flags.ignore_permissions = True
		payment_request.insert()

	return {"payment_request": payment_request}


@frappe.whitelist()
def generate_quotation_for_cart(cart: dict):
	if len(cart.get("items", [])) < 1:
		frappe.throw(frappe._("Can't checkout with empty cart"))
	
	# Check if user is authenticated
	current_user = frappe.session.user
	if current_user == "Guest":
		frappe.throw(frappe._("Please login to checkout"), frappe.PermissionError)
	
	# User is authenticated, proceed with cart quotation
	cart_quotation = get_quotation_for_cart(cart)
	# remove_coupon_code() is already called inside get_quotation_for_cart via _remove_coupon_code
	# No need to call it again here
	return cart_quotation


def get_quotation_for_cart(cart: dict):
	# Since we already checked authentication above, we can call _get_cart_quotation directly
	# If it raises a redirect, it might be because the user doesn't have a Customer/Contact
	# For authenticated users, we should create a quotation manually instead of redirecting
	try:
		unsaved_quotation_doc = _get_cart_quotation()
	except frappe.Redirect:
		# User is authenticated but _get_cart_quotation raised redirect (likely missing Customer/Contact)
		# Get or create the party/customer for the authenticated user
		from webshop.webshop.shopping_cart.cart import get_party, get_contact_name, get_fullname, get_debtors_account
		from webshop.webshop.doctype.webshop_settings.webshop_settings import get_shopping_cart_settings
		from frappe.utils.nestedset import get_root_of
		
		user = frappe.session.user
		contact_name = get_contact_name(user)
		party = None
		
		# Try to get existing party from contact
		if contact_name:
			contact = frappe.get_doc("Contact", contact_name)
			if contact.links:
				party_doctype = contact.links[0].link_doctype
				party = frappe.get_doc(party_doctype, contact.links[0].link_name)
		
		# If no party exists, create a Customer for the authenticated user
		if not party:
			cart_settings = get_shopping_cart_settings()
			
			# Create Customer
			customer = frappe.new_doc("Customer")
			fullname = get_fullname(user)
			customer.update({
				"customer_name": fullname,
				"customer_type": "Individual",
				"customer_group": cart_settings.default_customer_group,
				"territory": get_root_of("Territory"),
			})
			customer.append("portal_users", {"user": user})
			
			debtors_account = get_debtors_account(cart_settings) if cart_settings.enable_checkout else ""
			if debtors_account:
				customer.update({"default_debit_account": debtors_account})
			
			customer.flags.ignore_permissions = True
			customer.flags.ignore_mandatory = True
			customer.insert()
			
			# Create Contact and link to Customer
			contact = frappe.new_doc("Contact")
			contact.update({
				"first_name": frappe.get_value("User", user, "first_name") or "",
				"last_name": frappe.get_value("User", user, "last_name") or "",
				"email_id": frappe.get_value("User", user, "email"),
			})
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": customer.name,
			})
			contact.append("email_ids", {
				"email_id": frappe.get_value("User", user, "email"),
				"is_primary": 1,
			})
			contact.flags.ignore_permissions = True
			contact.flags.ignore_mandatory = True
			contact.insert()
			
			party = customer
		
		# Create quotation manually with the party
		quotation = frappe.new_doc("Quotation")
		quotation.party_name = party.name
		quotation.order_type = "Shopping Cart"
		quotation.quotation_to = "Customer"
		quotation.flags.ignore_permissions = True
		unsaved_quotation_doc = quotation
	sale_price_list = frappe.get_cached_value("Lifestyle Settings", "Lifestyle Settings", "sale_price_list")
	ecommerce_warehouse = frappe.get_cached_value(
		"Lifestyle Settings", "Lifestyle Settings", "ecommerce_warehouse"
	)
	unsaved_quotation_doc.selling_price_list = sale_price_list
	unsaved_quotation_doc.items = []
	for item in cart["items"]:
		item_code = item["variant"]["item_code"]
		item_rate = frappe.db.get_value("Item Price", {
			"item_code": item_code,
			"price_list": sale_price_list
		}, "price_list_rate") or frappe.db.get_value("Item", item_code, "standard_rate") or 0
		
		unsaved_quotation_doc.append(
			"items",
			{
				"item_code": item_code,
				"qty": item["qty"],
				"warehouse": ecommerce_warehouse,
				"price_list_rate": item_rate,
				"rate": item_rate,
			},
		)
	
	# Set missing values and calculate totals before saving
	unsaved_quotation_doc.flags.ignore_permissions = True
	unsaved_quotation_doc.flags.ignore_validate = True
	unsaved_quotation_doc.run_method("set_missing_values")
	unsaved_quotation_doc.run_method("calculate_taxes_and_totals")
	
	# Ensure base_grand_total is set (use 0 if still None)
	if not unsaved_quotation_doc.base_grand_total:
		unsaved_quotation_doc.base_grand_total = unsaved_quotation_doc.grand_total or 0
	if not unsaved_quotation_doc.base_rounded_total:
		unsaved_quotation_doc.base_rounded_total = unsaved_quotation_doc.rounded_total or unsaved_quotation_doc.base_grand_total
	
	unsaved_quotation_doc.save()
	# Remove any existing coupon code
	_remove_coupon_code(unsaved_quotation_doc)
	set_charges(unsaved_quotation_doc)
	# Final save after all calculations
	unsaved_quotation_doc.run_method("calculate_taxes_and_totals")
	return unsaved_quotation_doc.save()


def set_charges(quotation):
	shipping_rule = frappe.get_cached_value("Lifestyle Settings", "Lifestyle Settings", "shipping_rule")
	if shipping_rule:
		quotation.shipping_rule = shipping_rule
		quotation.run_method("apply_shipping_rule")
		quotation.run_method("calculate_taxes_and_totals")


def set_cod_charges(quotation):
	cod_charges_applicable_below, cod_charge = get_cod_configuration()
	account_head = frappe.get_cached_value("Lifestyle Settings", "Lifestyle Settings", "charge_account_head")
	if not cod_charges_applicable_below or not cod_charge:
		return
	if cod_charges_applicable_below < quotation.rounded_total:
		return
	if not account_head:
		frappe.throw("Please select a valid account for cod charges.")

	cod_charge = {
		"doctype": "Sales Taxes and Charges",
		"description": " Cash on Delivery Charges",
		"charge_type": "Actual",
		"account_head": account_head,
		"tax_amount": cod_charge,
	}
	quotation.append("taxes", cod_charge)
	quotation.calculate_taxes_and_totals()
	quotation.flags.ignore_permissions = True
	quotation.save()


@frappe.whitelist()
def update_quotation_address(address: dict):
	quotation = _get_cart_quotation()
	update_quotation_payment_terms_due_date(quotation)
	# Handle Store Pickup
	if address.get("is_store_pickup", False):
		quotation.custom_store = address.get("store_pickup_warehouse", "")
		quotation.custom_is_store_pickup = True
		quotation.save(ignore_permissions=True)

		return {
			"message": "Addresses updated successfully",
			"success": True,
		}
	quotation.custom_is_store_pickup = False
	quotation.custom_store = ""

	if address.get("billing_address", {}).get("is_saved"):
		billing_address_name = address.get("billing_address", {}).get("address_id")
	else:  # New Billing Address
		billing_address_doc = add_billing_address(quotation.party_name, address)
		billing_address_name = billing_address_doc.name

	quotation.customer_address = billing_address_name  # Link billing address

	# Handle Shipping Address
	if address.get("shipping_same_as_billing"):  # Use correct key for matching
		shipping_address_name = billing_address_name
	elif address.get("shipping_address", {}).get("is_saved"):
		shipping_address_name = address.get("shipping_address", {}).get("address_id")
	else:  # New Shipping Address
		shipping_address_doc = add_shipping_address(quotation.party_name, address)
		shipping_address_name = shipping_address_doc.name

	quotation.shipping_address_name = shipping_address_name  # Link shipping address

	# Handle Contact (Add Phone Number)
	contact = frappe.get_doc("Contact", quotation.contact_person)
	existing_phones = {entry.phone for entry in contact.phone_nos}

	# Add Billing Phone if not in existing contact
	billing_phone = address.get("billing_address", {}).get("phone_number")
	if billing_phone and billing_phone not in existing_phones:
		contact.append("phone_nos", {"phone": billing_phone})

	# Add Shipping Phone if not in existing contact
	shipping_phone = address.get("shipping_address", {}).get("phone_number")
	if shipping_phone and shipping_phone not in existing_phones:
		contact.append("phone_nos", {"phone": shipping_phone})

	contact.save(ignore_permissions=True)
	quotation.save(ignore_permissions=True)

	return {
		"message": "Addresses updated successfully",
		"success": True,
	}


@frappe.whitelist(allow_guest=True)
def confirm_payment(payment_mode: PaymentMode, reference_id: str):
	if payment_mode == payment_mode.COD:
		submit_quotation_and_create_order(reference_id, payment_mode)
		return {"status": "Paid"}

	if payment_mode == PaymentMode.TELR:
		payment_request = frappe.get_doc("Telr Payment Request", int(reference_id))
		payment_request.sync_status()

		if payment_request.status == "Paid":
			quote_name = payment_request.ref_docname
			submit_quotation_and_create_order(quote_name, payment_mode, payment_request.telr_order_ref)
		return payment_request

	if payment_mode == PaymentMode.TABBY:
		payment_request = frappe.get_doc("Tabby Payment Request", {"tabby_payment_id": reference_id})
		payment_request.sync_status()

		if payment_request.status == "AUTHORIZED":
			quote_name = payment_request.ref_docname
			payment_request.capture_payment()
			submit_quotation_and_create_order(quote_name, payment_mode, payment_request.tabby_order_ref)

		return payment_request

	if payment_mode == PaymentMode.YOCO:
		payment_request = frappe.get_doc("Yoco Payment Request", int(reference_id))
		payment_request.flags.ignore_permissions = True
		payment_request.sync_status()

		if payment_request.status == "Paid":
			quote_name = payment_request.ref_docname
			# Use yoco_charge_id first (where token is stored), fallback to yoco_order_id
			payment_reference = payment_request.yoco_charge_id or payment_request.yoco_order_id or str(payment_request.name)
			submit_quotation_and_create_order(quote_name, payment_mode, payment_reference)
		return payment_request

	if payment_mode == PaymentMode.PAYFAST:
		payment_request = frappe.get_doc("Payfast Payment Request", {"m_payment_id": reference_id})
		payment_request.flags.ignore_permissions = True
		payment_request.sync_status()

		if payment_request.status == "Complete":
			quote_name = payment_request.ref_docname
			submit_quotation_and_create_order(quote_name, payment_mode, payment_request.pf_payment_id or payment_request.m_payment_id)

		return payment_request


def submit_quotation_and_create_order(
	quote_name: str, payment_mode: PaymentMode, payment_reference: str = ""
):
	# Store ORIGINAL user at the very beginning - this is critical for session restoration
	original_session_user = frappe.session.user
	
	# Get quotation - if PermissionError, authenticate as the quotation owner
	# This handles cases where payment redirect returns as Guest user
	quotation_doc = None
	quotation_user_changed = False
	
	try:
		quotation_doc = frappe.get_doc("Quotation", quote_name)
	except frappe.PermissionError:
		# If permission denied, authenticate as the quotation owner
		owner = frappe.db.get_value("Quotation", quote_name, "owner")
		if owner and owner != "Administrator" and owner != original_session_user:
			frappe.set_user(owner)
			quotation_user_changed = True
			try:
				quotation_doc = frappe.get_doc("Quotation", quote_name)
			except frappe.PermissionError:
				# Still fails, use ignore_permissions
				quotation_doc = frappe.get_doc("Quotation", quote_name)
				quotation_doc.flags.ignore_permissions = True
		else:
			# Use ignore_permissions as fallback
			quotation_doc = frappe.get_doc("Quotation", quote_name)
			quotation_doc.flags.ignore_permissions = True
	
	# Set ignore_permissions for submit if not already set
	if not quotation_doc.flags.ignore_permissions:
		quotation_doc.flags.ignore_permissions = True
	
	try:
		if payment_mode == payment_mode.COD:
			set_cod_charges(quotation_doc)
		quotation_doc.submit()
	finally:
		# Restore to original user after quotation operations
		if quotation_user_changed:
			frappe.set_user(original_session_user)

	so = _make_sales_order(quote_name, ignore_permissions=True)
	so.custom_ecommerce_payment_mode = (
		payment_mode.title() if not payment_mode == payment_mode.COD else payment_mode.upper()
	)
	so.flags.ignore_permissions = True
	so.insert()

	if payment_mode != payment_mode.COD:
		so.submit()
		# Determine payment request doctype and reference field based on payment mode
		if payment_mode == PaymentMode.TELR:
			payment_request_doctype = "Telr Payment Request"
			payment_order_ref_field = "telr_order_ref"
		elif payment_mode == PaymentMode.TABBY:
			payment_request_doctype = "Tabby Payment Request"
			payment_order_ref_field = "tabby_order_ref"
		elif payment_mode == PaymentMode.YOCO:
			payment_request_doctype = "Yoco Payment Request"
			payment_order_ref_field = "yoco_charge_id"
		elif payment_mode == PaymentMode.PAYFAST:
			payment_request_doctype = "Payfast Payment Request"
			payment_order_ref_field = "m_payment_id"
		else:
			payment_request_doctype = None
			payment_order_ref_field = None

		if payment_request_doctype and payment_order_ref_field:
			payment_request = frappe.get_doc(
				payment_request_doctype, {payment_order_ref_field: payment_reference}
			)
			payment_request.flags.ignore_permissions = True
			payment_request.ref_docname = so.name
			payment_request.ref_doctype = "Sales Order"
			payment_request.save()
		
		# Create Payment Entry as Administrator (required for proper accounting)
		# Store current user before changing to Administrator
		payment_entry_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			pe = get_payment_entry("Sales Order", so.name, reference_date=frappe.utils.today())
			pe.flags.ignore_permissions = True
			pe.mode_of_payment = payment_mode.title()
			pe.reference_no = payment_reference
			pe.insert().submit()
		finally:
			# Always restore to ORIGINAL session user, not the intermediate one
			frappe.set_user(original_session_user)


@frappe.whitelist()
def apply_coupon_code(applied_code):
	quotation = True
	if not applied_code:
		frappe.throw(frappe._("Please enter a coupon code"))
	coupon_name = frappe.db.get_value("Coupon Code", {"coupon_code": applied_code}, "name")
	if not coupon_name:
		frappe.throw(frappe._("Please enter a valid coupon code"))
	validate_coupon_code(coupon_name)
	quotation = _get_cart_quotation()
	quotation.coupon_code = coupon_name
	quotation.flags.ignore_permissions = True
	quotation.save()
	return {"success": True, "message": frappe._("Coupon code applied successfully")}


@frappe.whitelist()
def remove_coupon_code():
	quotation = _get_cart_quotation()
	_remove_coupon_code(quotation)


def _remove_coupon_code(quotation):
	quotation.coupon_code = ""
	quotation.items = [item for item in quotation.items if not item.get("is_free_item")]
	for item in quotation.items:
		item.discount_percentage = 0
		item.discount_amount = 0
		item.distributed_discount_amount = 0
		if item.price_list_rate:
			item.rate = item.price_list_rate
	quotation.flags.ignore_permissions = True
	quotation.run_method("calculate_taxes_and_totals")
	# Ensure totals are set before saving
	if not quotation.base_grand_total:
		quotation.run_method("set_missing_values")
		quotation.run_method("calculate_taxes_and_totals")
	quotation.save()
	quotation.discount_amount = 0
	quotation.run_method("calculate_taxes_and_totals")
	quotation.save()


def add_billing_address(party_name, address):
	address_doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": f"Shop Billing Address - {party_name}",
			"address_type": "Billing",
			"city": address.get("billing_address", {}).get("city"),
			"country": address.get("billing_address", {}).get("country"),
			"address_line1": address.get("billing_address", {}).get("full_address"),
			"address_line2": address.get("billing_address", {}).get("landmark"),
			"pincode": address.get("billing_address", {}).get("po_box"),
			"phone": address.get("billing_address", {}).get("phone_number"),
			"email_id": address.get("billing_address", {}).get("email"),
			"first_name": address.get("billing_address", {}).get("first_name"),
			"last_name": address.get("billing_address", {}).get("last_name"),
		}
	).insert(ignore_permissions=True)
	return address_doc


def add_shipping_address(party_name, address):
	address_doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": f"Shop Shipping Address - {party_name}",
			"address_type": "Shipping",
			"city": address.get("shipping_address", {}).get("city"),
			"country": address.get("shipping_address", {}).get("country"),
			"address_line1": address.get("shipping_address", {}).get("full_address"),
			"address_line2": address.get("shipping_address", {}).get("landmark"),
			"pincode": address.get("shipping_address", {}).get("po_box"),
			"phone": address.get("shipping_address", {}).get("phone_number"),
			"email_id": address.get("shipping_address", {}).get("email"),
			"first_name": address.get("shipping_address", {}).get("first_name"),
			"last_name": address.get("shipping_address", {}).get("last_name"),
		}
	).insert(ignore_permissions=True)
	return address_doc


def update_quotation_payment_terms_due_date(quotation):
	today = getdate()
	for term in quotation.get("payment_schedule", []):
		if term.due_date and term.due_date < today:
			term.due_date = today


def update_delivery_charges(quotation):
	if quotation.custom_is_store_pickup:
		quotation.shipping_rule = None
		quotation.taxes = []
		quotation.calculate_taxes_and_totals()
		quotation.save(ignore_permissions=True)
	else:
		set_charges(quotation)
		quotation.save(ignore_permissions=True)


def is_yoco_configured():
	"""Check if Yoco payment gateway is configured"""
	try:
		settings_list = frappe.get_all("Yoco Settings", limit=1)
		if not settings_list:
			return False
		settings = frappe.get_doc("Yoco Settings", settings_list[0].name)
		return bool(settings.public_key and settings.get_password("secret_key", raise_exception=False))
	except Exception:
		return False


def is_payfast_configured():
	"""Check if Payfast payment gateway is configured"""
	try:
		settings_list = frappe.get_all("Payfast Settings", limit=1)
		if not settings_list:
			return False
		settings = frappe.get_doc("Payfast Settings", settings_list[0].name)
		return bool(settings.merchant_id and settings.merchant_key)
	except Exception:
		return False


@frappe.whitelist()
def get_yoco_payment_details(payment_request_name):
	"""Get Yoco payment details for modal display"""
	try:
		# Ensure payment_request_name is a string
		payment_request_name = str(payment_request_name)
		payment_request = frappe.get_doc("Yoco Payment Request", payment_request_name)
		
		# Verify user has access
		if frappe.session.user == "Guest":
			frappe.throw(frappe._("Please login to complete payment"), frappe.PermissionError)
		
		# Get Yoco Settings
		yoco_settings = payment_request.get_yoco_settings()
		
		# Get public key
		public_key = yoco_settings.get("public_key")
		if not public_key:
			frappe.throw(frappe._("Yoco Public Key not configured"), frappe.PermissionError)
		
		# Get quotation details
		quotation = frappe.get_doc(payment_request.ref_doctype, payment_request.ref_docname)
		
		# Ensure amount is set and is a valid number
		try:
			amount = float(payment_request.amount) if payment_request.amount else 0.0
		except (TypeError, ValueError):
			amount = 0.0
		
		if amount <= 0:
			frappe.throw(frappe._("Invalid payment amount"), frappe.ValidationError)
		
		return {
			"payment_request_name": payment_request_name,
			"amount": amount,
			"currency": payment_request.currency_code or "ZAR",
			"public_key": public_key,
			"reference_docname": quotation.name,
			"reference_doctype": quotation.doctype,
			"title": f"Payment for {quotation.name}",
			"description": f"Payment for {quotation.doctype} {quotation.name}",
			"enable_apple_pay": getattr(yoco_settings, "enable_apple_pay", False),
			"apple_pay_merchant_id": getattr(yoco_settings, "apple_pay_merchant_id", "") or ""
		}
	except Exception as e:
		frappe.log_error(
			f"Error getting Yoco payment details: {str(e)}\n{frappe.get_traceback()}",
			"Yoco Payment Details Error"
		)
		frappe.throw(frappe._("Failed to load payment details: {0}").format(str(e)))
