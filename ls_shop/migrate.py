import frappe


def after_install():
	create_payment_modes()
	try:
		create_default_email_templates()
	except Exception as e:
		import traceback

		error_msg = f"Error creating default email templates: {e!s}"
		frappe.log_error(traceback.format_exc(), "Lifestyle Shop Installation - Email Templates")
		frappe.errprint(error_msg)
		frappe.errprint(traceback.format_exc())


def create_payment_modes():
	modes = {"Telr", "Yoco", "Payfast"}

	for mode in modes:
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": mode,
				"enabled": True,
				"type": "Bank",
			}
		).insert(ignore_if_duplicate=True)


def create_default_email_templates():
	"""Create default email templates required by Lifestyle Settings"""

	email_templates = [
		{
			"name": "Order Confirmation",
			"subject": "Order Confirmation - {{ doc.name }}",
			"response": """Dear {{ doc.customer_name }},

Thank you for your order! Your order has been confirmed.

Order Details:
Order ID: {{ doc.name }}
Date: {{ doc.transaction_date }}
Total: {{ doc.grand_total }}

You can track your order status at: {{ login_url }}

Best regards,
{{ company }}""",
			"doctype": "Sales Order",
		},
		{
			"name": "Item In Stock",
			"subject": "Item Back in Stock - {{ item.item_name }}",
			"response": """Dear Customer,

Great news! The item "{{ item.item_name }}" is now back in stock.

You can purchase it now at: {{ item_url }}

Best regards,
{{ company }}""",
			"doctype": "Item",
		},
		{
			"name": "Order Cancellation",
			"subject": "Order Cancellation Confirmation - {{ doc.name }}",
			"response": """Dear {{ doc.customer_name }},

Your order {{ doc.name }} has been cancelled as requested.

If you have any questions, please contact our customer service.

Best regards,
{{ company }}""",
			"doctype": "Sales Order",
		},
	]

	for template_data in email_templates:
		if not frappe.db.exists("Email Template", template_data["name"]):
			template = frappe.get_doc({"doctype": "Email Template", **template_data})
			# Skip all validations and hooks to avoid triggering doctype validation
			template.flags.ignore_validate = True
			template.flags.ignore_links = True
			template.flags.ignore_mandatory = True
			template.flags.ignore_permissions = True
			# Use db_insert to bypass validation hooks
			try:
				template.db_insert()
				frappe.db.commit()
				frappe.errprint(f"Created Email Template: {template_data['name']}")
			except Exception as template_error:
				# If db_insert fails, try regular insert with all flags
				template.flags.ignore_validate = True
				template.flags.ignore_links = True
				template.flags.ignore_mandatory = True
				template.insert(ignore_permissions=True, ignore_validate=True, ignore_links=True)
				frappe.errprint(f"Created Email Template: {template_data['name']}")
		else:
			frappe.errprint(f"Email Template '{template_data['name']}' already exists")
