// Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Job Work Out", {
    setup(frm){
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'source_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
    },
    customer(frm){
        get_address(frm, "Customer", frm.doc.customer, 'customer_address', 'customer_address_details');
    },
    company(frm){
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'source_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
    },
    job_work_out_from(frm){
        list_of_table_remove = ['job_work_in_item_details', 'job_work_out_finished_item_details', 'job_work_out_raw_items_details', 'job_work_out_rejection_reason', 'job_work_out_raw_item_details', 'job_work_out_bifurcation_details']
        list_of_table_remove.forEach(function(table_name) {
            frm.clear_table(table_name);
            frm.refresh_field(table_name);
        });
    },
    get_in_challan(frm){
        frappe.call({
            method: 'get_job_work_in_challan_for_above_items',
            doc: frm.doc,
            callback: function(resp){
                frm.refresh_field('job_work_in_item_details')
                frm.refresh_field('job_work_out_raw_items_details')
                frm.refresh_field('job_work_out_rejection_reason')
            }
        });
    }
});

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

function set_filters(frm, DocTypeFieldName, DocTypeField, filters){
    if(DocTypeField !== 'None'){
        frm.set_query(DocTypeFieldName, DocTypeField, function(doc, cdt, cdn) {
            return {
                filters: filters
            };
        });
    } else{
        frm.set_query(DocTypeFieldName, function(doc) {
            return {
                filters: filters,
            };
        });
    }
}


frappe.ui.form.on('Job Work Out Rejection Reason', {
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
                'rej': d.rejection_type
            },
            callback: function(r){
                refresh_field('job_work_out_rejection_reason')
            }
        })
    }
});


frappe.ui.form.on('Job Work Out Finished Item Details', {
    ok_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'get_required_raw_item_of_finished_ok_qty',
            doc: frm.doc,
            callback: function(resp){
                frm.refresh_field('job_work_out_raw_item_details');
            }
        });
    },
});

frappe.ui.form.on('Job Work Out Raw Items Details', {
    cr_qty(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        get_rejection_reason_for_rejected_qty(frm, d.item_code, d.cr_qty, 'cr_qty');
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
            frm.refresh_field('job_work_out_rejection_reason');
        }
    });
}