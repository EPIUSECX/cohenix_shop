# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_url_to_form


class LifestyleSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from ls_shop.lifestyle_shop_ecommerce.doctype.footer_section_mapping.footer_section_mapping import (
			FooterSectionMapping,
		)
		from ls_shop.lifestyle_shop_ecommerce.doctype.item_group_map.item_group_map import ItemGroupMap
		from ls_shop.lifestyle_shop_ecommerce.doctype.return_reason.return_reason import ReturnReason

		accent_color: DF.Color | None
		attribute_name_field: DF.Data | None
		badge_bg_color: DF.Color | None
		based_on_attribute: DF.Link | None
		border_accent_color: DF.Color | None
		brand_logo: DF.AttachImage | None
		brand_text_color: DF.Color | None
		button_bg_color: DF.Color | None
		cc_email: DF.Data | None
		charge_account_head: DF.Link | None
		cod_charge: DF.Currency
		cod_charge_applicable_below: DF.Currency
		cod_enabled: DF.Check
		contact_email: DF.Data | None
		contact_phone: DF.Data | None
		copyright_text: DF.Data | None
		create_variants_automatically_on_configurator_creation: DF.Check
		default_price_list: DF.Link | None
		ecommerce_item_group_mapping: DF.Table[ItemGroupMap]
		ecommerce_warehouse: DF.Link | None
		facebook_url: DF.Data | None
		favicon: DF.Attach | None
		focus_ring_color: DF.Color | None
		footer_bg_color: DF.Color | None
		footer_logo: DF.AttachImage | None
		footer_sections: DF.Table[FooterSectionMapping]
		footer_text_color: DF.Color | None
		form_accent_color: DF.Color | None
		heading_accent_color: DF.Color | None
		instagram_url: DF.Data | None
		item_in_stock_email_template: DF.Link
		link_color: DF.Color | None
		link_hover_color: DF.Color | None
		logo_url: DF.Data | None
		newsletter_description: DF.Text | None
		newsletter_title: DF.Data | None
		order_cancellation_email_template: DF.Link
		order_confirmation_email_template: DF.Link
		payment_methods_image: DF.AttachImage | None
		primary_color: DF.Color | None
		primary_hover_color: DF.Color | None
		print_format: DF.Link | None
		reason_for_return: DF.Table[ReturnReason]
		return_period: DF.Int
		sale_price_list: DF.Link | None
		secondary_accent_color: DF.Color | None
		shipping_rule: DF.Link | None
		snapchat_url: DF.Data | None
		store_name: DF.Data | None
		strikethrough_color: DF.Color | None
		tabby_enabled: DF.Check
		telr_enabled: DF.Check
		tiktok_url: DF.Data | None
		twitter_url: DF.Data | None
		vat_certificate_image: DF.AttachImage | None
		working_hours: DF.Data | None
	# end: auto-generated types

	pass

	def validate(self):
		if not (
			self.telr_enabled 
			or self.tabby_enabled 
			or self.yoco_enabled 
			or self.payfast_enabled 
			or self.cod_enabled
		):
			frappe.throw(frappe._("At least one payment method (Telr, Tabby, Yoco, Payfast, or COD) must be enabled."))

	def get_default_price_list(self):
		return (
			self.default_price_list
			if self.default_price_list
			else frappe.get_cached_value("Webshop Settings", "Webshop Settings", "price_list")
		)

	def get_sale_price_list(self):
		return (
			self.sale_price_list
			if self.sale_price_list
			else frappe.get_cached_value("Webshop Settings", "Webshop Settings", "price_list")
		)

	@frappe.whitelist()
	def enqueue_publish_all_variants(self, attribute: str):
		log = create_configurator_log()
		frappe.enqueue(
			"ls_shop.lifestyle_shop_ecommerce.doctype.lifestyle_settings.lifestyle_settings.generate_configurators_for_all_templates",
			queue="long",
			attribute=attribute,
			log_name=log.name,
		)
		link = get_url_to_form("Bulk Style Attribute Configurator Creation Log", log.name)

		return frappe._(f"Creating configurators. <a href='{link}'>View Log</a>")

	@frappe.whitelist()
	def sync_item_group_mapping_to_ecommerce_items(self):
		for mapping in self.ecommerce_item_group_mapping:
			frappe.db.set_value(
				"Style Attribute Variant",
				{"item_group": mapping.original_item_group},
				"item_group",
				mapping.ecommerce_item_group,
			)

	@frappe.whitelist()
	def install_demo_data(self):
		"""Install demo data for testing LS Shop"""
		from ls_shop.install_demo_data import install_demo_data

		frappe.enqueue(
			install_demo_data,
			queue="long",
			timeout=3000,
		)

		return "Demo data installation has been queued. This may take a few minutes. Check the background jobs for progress."

	@frappe.whitelist()
	def publish_all_items(self):
		"""Publish all items to website"""
		from ls_shop.publish_demo_items import publish_all_demo_items

		frappe.enqueue(
			publish_all_demo_items,
			queue="default",
			timeout=600,
		)

		return "Publishing all items to website. This may take a moment. Refresh the page after completion."

	def generate_theme_css(self):
		"""Generate CSS custom properties from color scheme settings"""
		return f"""
		<style>
		:root {{
			--ls-primary: {self.primary_color or '#b91c1c'};
			--ls-primary-hover: {self.primary_hover_color or '#991b1b'};
			--ls-link: {self.link_color or '#7f1d1d'};
			--ls-link-hover: {self.link_hover_color or '#991b1b'};
			--ls-accent: {self.accent_color or '#b91c1c'};
			--ls-border-accent: {self.border_accent_color or '#b91c1c'};
			--ls-button-bg: {self.button_bg_color or '#b91c1c'};
			--ls-strikethrough: {self.strikethrough_color or '#b91c1c'};
			--ls-badge-bg: {self.badge_bg_color or '#b91c1c'};
			--ls-heading-accent: {self.heading_accent_color or '#991b1b'};
			--ls-brand-text: {self.brand_text_color or '#b91c1c'};
			--ls-secondary-accent: {self.secondary_accent_color or '#991b1b'};
			--ls-form-accent: {self.form_accent_color or '#b91c1c'};
			--ls-focus-ring: {self.focus_ring_color or '#b91c1c'};
			--ls-carousel-dot: {self.accent_color or '#b91c1c'};
			--ls-footer-bg: {self.footer_bg_color or '#111827'};
			--ls-footer-text: {self.footer_text_color or '#ffffff'};
		}}

		/* Primary color utilities */
		.bg-primary {{ background-color: var(--ls-primary) !important; }}
		.text-primary {{ color: var(--ls-primary) !important; }}
		.border-primary {{ border-color: var(--ls-primary) !important; }}
		.hover\\:bg-primary-hover:hover {{ background-color: var(--ls-primary-hover) !important; }}
		.hover\\:text-primary-hover:hover {{ color: var(--ls-primary-hover) !important; }}
		.focus\\:border-primary:focus {{ border-color: var(--ls-primary) !important; }}

		/* Link color utilities */
		.text-link {{ color: var(--ls-link) !important; }}
		.hover\\:text-link-hover:hover {{ color: var(--ls-link-hover) !important; }}

		/* Accent color utilities */
		.bg-accent {{ background-color: var(--ls-accent) !important; }}
		.text-accent {{ color: var(--ls-accent) !important; }}
		.border-accent {{ border-color: var(--ls-border-accent) !important; }}
		.hover\\:bg-accent:hover {{ background-color: var(--ls-accent) !important; }}

		/* UI Element utilities */
		.bg-button {{ background-color: var(--ls-button-bg) !important; }}
		.text-strikethrough {{ color: var(--ls-strikethrough) !important; }}
		.bg-badge {{ background-color: var(--ls-badge-bg) !important; }}
		.text-heading-accent {{ color: var(--ls-heading-accent) !important; }}
		.text-brand {{ color: var(--ls-brand-text) !important; }}
		.text-secondary-accent {{ color: var(--ls-secondary-accent) !important; }}
		.bg-secondary-accent {{ background-color: var(--ls-secondary-accent) !important; }}
		.border-secondary-accent {{ border-color: var(--ls-secondary-accent) !important; }}
		.hover\\:bg-secondary-accent:hover {{ background-color: var(--ls-secondary-accent) !important; }}
		.accent-form {{ accent-color: var(--ls-form-accent) !important; }}
		.focus\\:ring-focus:focus {{ box-shadow: 0 0 0 2px var(--ls-focus-ring) !important; }}

		/* Footer utilities */
		.bg-footer {{ background-color: var(--ls-footer-bg) !important; }}
		.text-footer {{ color: var(--ls-footer-text) !important; }}
		</style>
		"""


def generate_configurators_for_all_templates(attribute: str, log_name: str):
	item = frappe.qb.DocType("Item")
	configurator = frappe.qb.DocType("Style Attribute Configurator")

	query = (
		frappe.qb.from_(item)
		.left_join(configurator)
		.on(item.name == configurator.item_template)
		.select(item.name)
		.where(configurator.item_template.isnull() & item.has_variants)
	)
	results = query.run(as_dict=True)
	configurator_log = frappe.get_doc("Bulk Style Attribute Configurator Creation Log", log_name)
	configurator_log.configurators = []

	for row in results:
		item_name = row.get("name")
		configurator = frappe.get_doc(
			{
				"doctype": "Style Attribute Configurator",
				"item_template": item_name,
				"item_attribute": attribute,
			}
		).insert(ignore_permissions=True)
		variants_generated = configurator.get_total_variants()
		frappe.db.commit()
		configurator_log.append(
			"configurators",
			{
				"style_attribute_configurator": configurator.name,
				"variants_created": variants_generated,
			},
		)
		configurator_log.save()


def create_configurator_log():
	return frappe.get_doc(
		{
			"doctype": "Bulk Style Attribute Configurator Creation Log",
		}
	).insert(ignore_permissions=True)
