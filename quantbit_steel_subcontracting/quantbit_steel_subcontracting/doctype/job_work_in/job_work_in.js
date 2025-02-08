// Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

let sales_order = [];
frappe.ui.form.on("Job Work In", {
    onload(frm){
        if(!frm.doc.customer_address && frm.doc.customer){
            get_address(frm, "Customer", frm.doc.customer, 'customer_address', 'customer_address_details');
        }
        if(!frm.doc.company_address && frm.doc.company){
            get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
        }
    },
    setup(frm){
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'sales_order', 'None',[['Sales Order', 'name', 'in', sales_order]])
    },
	async customer(frm) {
        // set_filters(frm, 'sales_order', 'None',[['Sales Order', 'customer', '=', frm.doc.customer],['Sales Order', 'custom_is_job_work', '=', 1]])
        if(frm.doc.customer){
            get_address(frm, "Customer", frm.doc.customer, 'customer_address', 'customer_address_details');
        }
        await frm.call({
            method: 'get_filtered_sales_order',
            doc: frm.doc,
            callback: function(resp){
                if(resp.message){
                    sales_order = resp.message;
                    set_filters(frm, 'sales_order', 'None',[['Sales Order', 'name', 'in', sales_order]])
                }
            }
        })
	},
    async company(frm) {
        set_filters(frm, 'source_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        if(frm.doc.company){
            get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
        }
        await frm.call({
            method: 'get_filtered_sales_order',
            doc: frm.doc,
            callback: function(resp){
                if(resp.message){
                    sales_order = resp.message;
                    set_filters(frm, 'sales_order', 'None',[['Sales Order', 'name', 'in', sales_order]])
                }
            }
        })
	},
    async sales_order(frm){
        // set_filters(frm, 'sales_order', 'None',[['Sales Order', 'customer', '=', frm.doc.customer],['Sales Order', 'custom_is_job_work', '=', 1]])
        set_filters(frm, 'sales_order', 'None',[['Sales Order', 'name', 'in', sales_order]])
        if (frm.doc.target_warehouse && frm.doc.sales_order) {
            get_out_type_items_details(frm, "Sales Order", 'sales_order','jwi_so_item_details')
        } else {
            frappe.msgprint("You have not selected target warehouse.Please select target warehouse first.")
            return
        }
    },
    target_warehouse(frm){
        set_target_warehouse_in_child_table(frm, 'jwi_so_item_details');
    },
});

frappe.ui.form.on("Job Work In Sales Order Item Details", {
    jwi_so_item_details_add(frm){
        set_target_warehouse_in_child_table(frm, 'jwi_so_item_details');
    },
    quantity(frm, cdt, cdn){
        let row = locals[cdt][cdn];
        if(row.quantity){
            row.amount = row.quantity * row.rate;
            row.total_weight = row.quantity * row.weight_per_unit;
        }
        frm.refresh_fields()
    },
    rate(frm, cdt, cdn){
        let row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            row.amount = row.quantity * row.rate;
        }
        frm.refresh_fields()
    }
})

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

function set_target_warehouse_in_child_table(frm, table_name) {
    frm.doc[table_name].forEach(function(row) {
        row.target_warehouse = frm.doc.target_warehouse;
    });
    frm.refresh_field(table_name);
}

function get_out_type_items_details(frm, Doctype, FieldName, Table){
    frappe.call({
        method: 'get_out_type_items_details',
        doc: frm.doc,
        args: {
            Doctype: Doctype,
            FieldName: FieldName,
            Table: Table
        },
        callback: function(resp){
            frm.refresh_field(Table);
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

frappe.ui.form.on("Job Work In Sales Order Item Details", {
    rate(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            frappe.model.set_value(cdt, cdn, 'amount', row.quantity * row.rate)
        } 
    }
})
