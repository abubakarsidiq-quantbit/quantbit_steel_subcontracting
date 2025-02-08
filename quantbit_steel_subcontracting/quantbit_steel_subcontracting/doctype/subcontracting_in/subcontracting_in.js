// Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Subcontracting In", {
    onload(frm){
        if(!frm.doc.supplier_address && frm.doc.supplier_id && frm.doc.docstatus == 0){
            get_address(frm, "Supplier", frm.doc.supplier_id, 'supplier_address', 'supplier_address_details');
        }
        if(!frm.doc.company_address && frm.doc.company && frm.doc.docstatus == 0){
            get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
        }
    },
    setup(frm){
        set_filters(frm, 'target_warehouse', 'None', 'Warehouse', 'company', '=', frm.doc.company)
    },
	supplier_id(frm) {
        if(frm.doc.source_warehouse && frm.doc.supplier_id){
            get_address(frm, "Supplier", frm.doc.supplier_id, 'supplier_address', 'supplier_address_details');
            get_out_challan_entries(frm);
        } else {
            frappe.msgprint("Please Source Warehouse First")
        }
	},
    get_out_items(frm){
        if(frm.doc.source_warehouse){
            get_out_challan_entries(frm);
        } else {
            frappe.msgprint("Please Source Warehouse First")
        }
    },
    refresh: function (frm) {
        const out_addRowButton = frm.fields_dict['subcontracting_out_item_details'].grid.wrapper.find('.grid-add-row');
        out_addRowButton.off('click').on('click', function (e) {
            e.stopImmediatePropagation();
            frappe.show_alert("<b>You Can`t Add Row To This Table</b> Select Supplier And Check The Challan You Want to <b>IN</b>")
        });
    },
    get_in_items(frm){
        get_item_from_out_item_check_mark(frm)
    },
    company(frm) {
        if(frm.doc.company){
            set_filters(frm, 'target_warehouse', 'None', 'Warehouse', 'company', '=', frm.doc.company);
            get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
            frm.call({
                method: 'get_account_and_description',
                doc: frm.doc
            })
        }
	},
});


function get_out_challan_entries(frm) {
    frappe.call({
        method: 'get_out_challan_entries', 
        doc: frm.doc,
        callback: function(resp) {
            frm.refresh_field('subcontracting_out_item_details');
        }
    });
}

function set_filters(frm, DocTypeFieldName, DocTypeField, Doctype, FilterField, Condition, Values){
    if(DocTypeField !== 'None'){
        frm.set_query(DocTypeFieldName, DocTypeField, function(doc, cdt, cdn) {
            return {
                filters: [
                    [Doctype, FilterField, Condition, Values],
                ]
            };
        });
    } else{
        frm.set_query(DocTypeFieldName, function(doc) {
            return {
                filters: [
                    [Doctype, FilterField, Condition, Values],
                ]
            };
        });
    }
}


function get_item_from_out_item_check_mark(frm) {
    frappe.call({
        method: 'get_item_from_out_item_check_mark', 
        doc: frm.doc,
        callback: function(resp) {
            frm.refresh_field('subcontracting_in_rejection_reason');
            frm.refresh_field('subcontracting_in_raw_item_details');
            frm.refresh_field('subcontracting_in_finished_item_details');
            if(resp.message){
                set_filters(frm, 'item_code', 'subcontracting_in_finished_item_details', 'Item', 'name', 'in', resp.message);
            }
        }
    });
}

frappe.ui.form.on('Subcontracting In Finished Item Details', {
    ok_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        get_required_raw_item_of_finished_ok_qty(frm, d.item_code, d.ok_qty, d.is_subcontracting_product_mix, d.subcontracting_product_mix);
    },
    cr_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        get_rejection_reason_for_rejected_qty(frm, d.item_code, d.cr_qty,'cr_qty');
    },
    mr_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        get_rejection_reason_for_rejected_qty(frm, d.item_code, d.mr_qty, 'mr_qty');
    },
    rw_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        get_rejection_reason_for_rejected_qty(frm, d.item_code, d.rw_qty, 'rw_qty');
    },
});

frappe.ui.form.on('Subcontracting In Rejection Reason', {
    rejection_quantity(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        if (!d.rejection_quantity || isNaN(d.rejection_quantity) || d.rejection_quantity <= 0) {
            frappe.msgprint(__('Please enter a valid rejection quantity.'));
            return;
        }
        frm.call({
            method: 'get_rejection_bifurgation',
            doc: frm.doc,
            args:{
                'item': d.item_code,
                'rej': d.rejection_type,
                'qty': d.rejection_quantity
            },
            callback: function(r){
                refresh_field('subcontracting_in_rejection_reason')
            }
        })
    }
});

function get_required_raw_item_of_finished_ok_qty(frm, item, ok_qty, is_subcontracting_product_mix, subcontracting_product_mix) {
    frappe.call({
        method: 'get_required_raw_item_of_finished_ok_qty',
        doc: frm.doc,
        args: {
            ok_qty: ok_qty,
            item: item,
            is_subcontracting_product_mix: is_subcontracting_product_mix,
            subcontracting_product_mix: subcontracting_product_mix
        },
        callback: function(resp){
            frm.refresh_field('subcontracting_in_raw_item_details');
        }
    });
}

function get_rejection_reason_for_rejected_qty(frm, item, qty, field) {
    frappe.call({
        method: 'get_rejection_reason_for_rejected_qty',
        doc: frm.doc,
        args: {
            item: item,
            qty: qty,
            field: field
        },
        callback: function(resp){
            frm.refresh_field('subcontracting_in_rejection_reason');
        }
    });
}

function get_address(frm, Doctype, DocName, AddressFieldName, DetailsFieldName){
    frappe.call({
        method: 'get_address',
        doc: frm.doc,
        args: {
            Doctype: Doctype,
            DocName: DocName,
        },
        callback: function(resp){
            if(resp.message){
                frm.set_value(AddressFieldName, resp.message[0]);
                frm.set_value(DetailsFieldName, resp.message[1]);
            }
        }
    });
}