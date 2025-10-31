// Copyright (c) 2024, Frappe Technologies and contributors
// License: MIT. See LICENSE

frappe.ui.form.on('Yoco Settings', {
	refresh: function(frm) {
        frm.add_custom_button(__('Test Connection'), function() {
            frm.call({
                method: 'test_connection',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message && r.message.status === 'success') {
                        frappe.msgprint(__('Connection successful!'));
                    } else {
                        frappe.msgprint(__('Connection failed: ') + (r.message?.message || __('Unknown error')), __('Error'));
                    }
                }
            });
        });
    }
});

