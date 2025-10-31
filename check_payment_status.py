#!/usr/bin/env python3
import frappe

# Connect to site
frappe.connect()

print("=" * 80)
print("PAYMENT PROCESS STATUS CHECK")
print("=" * 80)

# Get recent Yoco Payment Requests
print("\n=== Recent Yoco Payment Requests ===")
yoco_payments = frappe.db.sql("""
    SELECT name, status, ref_docname, ref_doctype, amount, yoco_charge_id, yoco_order_id, creation
    FROM `tabYoco Payment Request`
    ORDER BY creation DESC
    LIMIT 5
""", as_dict=True)

if yoco_payments:
    for p in yoco_payments:
        print(f"ID: {p['name']}")
        print(f"  Status: {p['status']}")
        print(f"  Ref: {p['ref_doctype']} {p['ref_docname']}")
        print(f"  Amount: {p['amount']}")
        print(f"  Charge ID: {p['yoco_charge_id']}")
        print(f"  Order ID: {p['yoco_order_id']}")
        print(f"  Created: {p['creation']}")
        print()
else:
    print("No Yoco Payment Requests found")

# Get recent Quotations
print("\n=== Recent Quotations ===")
quotations = frappe.db.sql("""
    SELECT name, status, docstatus, customer_name, grand_total, rounded_total, creation
    FROM `tabQuotation`
    ORDER BY creation DESC
    LIMIT 5
""", as_dict=True)

if quotations:
    for q in quotations:
        print(f"Name: {q['name']}")
        print(f"  Status: {q['status']}")
        print(f"  DocStatus: {q['docstatus']} (0=Draft, 1=Submitted, 2=Cancelled)")
        print(f"  Customer: {q['customer_name']}")
        print(f"  Total: {q['grand_total']}")
        print(f"  Rounded Total: {q['rounded_total']}")
        print(f"  Created: {q['creation']}")
        print()
else:
    print("No Quotations found")

# Get recent Sales Orders
print("\n=== Recent Sales Orders ===")
sales_orders = frappe.db.sql("""
    SELECT name, status, docstatus, customer, custom_ecommerce_payment_mode, grand_total, creation
    FROM `tabSales Order`
    ORDER BY creation DESC
    LIMIT 5
""", as_dict=True)

if sales_orders:
    for so in sales_orders:
        print(f"Name: {so['name']}")
        print(f"  Status: {so['status']}")
        print(f"  DocStatus: {so['docstatus']} (0=Draft, 1=Submitted, 2=Cancelled)")
        print(f"  Customer: {so['customer']}")
        print(f"  Payment Mode: {so['custom_ecommerce_payment_mode']}")
        print(f"  Total: {so['grand_total']}")
        print(f"  Created: {so['creation']}")
        print()
else:
    print("No Sales Orders found")

# Check Payment Request to Sales Order links - improved query
print("\n=== Payment Request to Sales Order Links ===")
# First get payment requests with their current references
yoco_prs = frappe.get_all("Yoco Payment Request", 
    fields=["name", "status", "ref_docname", "ref_doctype", "yoco_charge_id"],
    order_by="creation desc",
    limit=5
)

for pr in yoco_prs:
    print(f"Payment Request: {pr.name}")
    print(f"  Payment Status: {pr.status}")
    print(f"  Current Ref: {pr.ref_doctype} {pr.ref_docname}")
    print(f"  Charge ID: {pr.yoco_charge_id}")
    
    # Check if ref_docname points to a Sales Order
    if pr.ref_doctype == "Sales Order":
        so = frappe.get_doc("Sales Order", pr.ref_docname)
        print(f"  ✅ Linked Sales Order: {so.name}")
        print(f"    SO Status: {so.status}")
        print(f"    SO DocStatus: {so.docstatus}")
        print(f"    Payment Mode: {so.custom_ecommerce_payment_mode}")
    elif pr.ref_doctype == "Quotation":
        # Check if quotation has been converted to Sales Order
        qtn = frappe.get_doc("Quotation", pr.ref_docname)
        so_list = frappe.db.get_all("Sales Order", 
            filters={"prevdoc_docname": qtn.name},
            fields=["name", "status", "docstatus", "custom_ecommerce_payment_mode"]
        )
        if so_list:
            so = so_list[0]
            print(f"  ✅ Quotation {qtn.name} -> Sales Order: {so.name}")
            print(f"    SO Status: {so.status}")
            print(f"    SO DocStatus: {so.docstatus}")
            print(f"    Payment Mode: {so.custom_ecommerce_payment_mode}")
        else:
            print(f"  ⚠️  Quotation {qtn.name} not yet converted to Sales Order")
    else:
        print(f"  ⚠️  Reference type unknown: {pr.ref_doctype}")
    print()

# Check Payment Entries
print("\n=== Recent Payment Entries ===")
pe_list = frappe.get_all("Payment Entry",
    fields=["name", "party", "paid_amount", "mode_of_payment", "reference_no", "docstatus"],
    order_by="creation desc",
    limit=5
)

for pe_doc in pe_list:
    pe = frappe.get_doc("Payment Entry", pe_doc.name)
    print(f"Payment Entry: {pe.name}")
    print(f"  Party: {pe.party}")
    print(f"  Amount: {pe.paid_amount}")
    print(f"  Mode: {pe.mode_of_payment}")
    print(f"  Ref No: {pe.reference_no}")
    print(f"  DocStatus: {pe.docstatus}")
    if pe.references:
        for ref in pe.references:
            print(f"  Linked to: {ref.reference_doctype} {ref.reference_name}")
    print()

print("\n" + "=" * 80)
print("Check complete!")
print("=" * 80)

