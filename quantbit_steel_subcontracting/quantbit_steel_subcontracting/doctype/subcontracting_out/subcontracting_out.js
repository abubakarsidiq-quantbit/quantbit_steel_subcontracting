// Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

let purchase_orders = [];
frappe.ui.form.on("Subcontracting Out", {
    setup(frm){
        set_filters(frm, 'purchase_order', 'None',[['Purchase Order', 'name', 'in', purchase_orders]])
        set_filters(frm, 'source_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
    },
	company(frm) {
        set_filters(frm, 'target_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'source_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company],['Warehouse', 'is_group', '=', 0]])
        set_filters(frm, 'purchase_order', 'None',[['Purchase Order', 'name', 'in', purchase_orders]])
        get_address(frm, "Company", frm.doc.company, 'company_address', 'company_address_details');
	},
    async supplier_id(frm) {
        set_filters(frm, 'open_order', 'None', [['Open Order', 'supplier_id', '=', frm.doc.supplier_id]])
        get_address(frm, "Supplier", frm.doc.supplier_id, 'supplier_address', 'supplier_address_details');
        await frm.call({
            method: 'get_filtered_purchase_order',
            doc: frm.doc,
            callback: function(resp){
                if(resp.message){
                    purchase_orders = resp.message;
                    set_filters(frm, 'purchase_order', 'None',[['Purchase Order', 'name', 'in', purchase_orders]])
                }
            }
        })
	},
    source_warehouse(frm){
        set_source_warehouse_in_child_table(frm, 'subcontracting_out_po_item_details');
        set_source_warehouse_in_child_table(frm, 'subcontracting_out_oo_item_details');
    },
    purchase_order(frm){
        set_filters(frm, 'purchase_order', 'None',[['Purchase Order', 'name', 'in', purchase_orders]])
        if (frm.doc.source_warehouse && frm.doc.purchase_order) {
            get_purchase_order_items_details(frm, "Purchase Order", 'purchase_order','subcontracting_out_po_item_details')
        } else {
            frappe.msgprint("You have not selected source warehouse.Please select source warehouse first.")
            return
        }
    },
    open_order(frm){
        set_filters(frm, 'open_order', 'None', [['Open Order', 'supplier_id', '=', frm.doc.supplier_id]])
        if (frm.doc.source_warehouse && frm.doc.open_order) {
            get_open_order_items_details(frm, "Open Order", 'open_order','subcontracting_out_oo_item_details')
        } else {
            frappe.msgprint("You have not selected source warehouse.Please select source warehouse first.")
        }
    },
});

frappe.ui.form.on("Subcontracting Out Purchase Order Item Details", {
    subcontracting_out_po_item_details_add(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (frm.doc.source_warehouse) {
            frappe.model.set_value(cdt, cdn, 'source_warehouse', frm.doc.source_warehouse);
        } else{
            frappe.msgprint("You have not selected source warehouse.Please select source warehouse first.")
        }
    },
    item_code(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.source_warehouse && row.item_code) {
            get_available_quantity(frm, cdt, cdn, row.item_code, row.source_warehouse, 'available_quantity')
            get_subcontracting_product_mix(frm, cdt, cdn, row.item_code, 'subcontracting_product_mix')
        }
    },
    source_warehouse(frm, cdt, cdn){
        let row = locals[cdt][cdn];
        if(row.source_warehouse && row.item_code) {
            get_available_quantity(frm, cdt, cdn, row.item_code, row.source_warehouse, 'available_quantity')
        }
    },
    quantity(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            frappe.model.set_value(cdt, cdn, 'amount', row.quantity * row.rate)
        }
        if(row.quantity && row.weight_per_unit){
            frappe.model.set_value(cdt, cdn, 'total_weight', row.quantity * row.weight_per_unit)
        }
        if(row.item_code){
            if(row.quantity > row.available_quantity){
                frappe.model.set_value(cdt, cdn, 'quantity', 0);
                frappe.msgprint("You have entered a quantity greater than the available stock.")
            }
        } else{
            frappe.throw("You have not selected item.")
        }
    },
    rate(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            frappe.model.set_value(cdt, cdn, 'amount', row.quantity * row.rate)
        } else {
            frappe.model.set_value(cdt, cdn, 'amount', 0)
        }
    }
});

frappe.ui.form.on("Subcontracting Out Open Order Item Details", {
    subcontracting_out_oo_item_details_add(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (frm.doc.source_warehouse) {
            frappe.model.set_value(cdt, cdn, 'source_warehouse', frm.doc.source_warehouse);
        } else{
            frappe.msgprint("You have not selected source warehouse.Please select source warehouse first.")
        }
    },
    item_code(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.source_warehouse && row.item_code) {
            get_available_quantity(frm, cdt, cdn, row.item_code, row.source_warehouse, 'available_quantity')
            get_subcontracting_product_mix(frm, cdt, cdn, row.item_code, 'subcontracting_product_mix')
        }
    },
    source_warehouse(frm, cdt, cdn){
        if(row.source_warehouse && row.item_code) {
            get_available_quantity(frm, cdt, cdn, row.item_code, row.source_warehouse, 'available_quantity')
        }
    },
    quantity(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.item_code){
            if(row.quantity > row.available_quantity){
                frappe.model.set_value(cdt, cdn, 'quantity', 0);
                frappe.msgprint("You have entered a quantity greater than the available stock.")
            }
        } else{
            frappe.throw("You have not selected item.")
        }
    }
});

frappe.ui.form.on('Subcontracting Out Open Order Item Details', {
    quantity(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            frappe.model.set_value(cdt, cdn, 'amount', row.quantity * row.rate)
        }
    },
    rate(frm, cdt, cdn){
        var row = locals[cdt][cdn];
        if(row.quantity && row.rate){
            frappe.model.set_value(cdt, cdn, 'amount', row.quantity * row.rate)
        }
    }
})

function set_source_warehouse_in_child_table(frm, table_name) {
    frm.doc[table_name].forEach(function(row) {
        row.source_warehouse = frm.doc.source_warehouse;
    });
    frm.refresh_field(table_name);
}

function get_open_order_items_details(frm, Doctype, FieldName, Table){
    frappe.call({
        method: 'get_open_order_items_details',
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

function get_purchase_order_items_details(frm, Doctype, FieldName, Table){
    frappe.call({
        method: 'get_purchase_order_items_details',
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

function get_available_quantity(frm, cdt, cdn, ItemCode, Warehouse, FieldName){
    frm.call({
        method: 'get_available_quantity',
        doc: frm.doc,
        args: {
            ItemCode: ItemCode,
            Warehouse: Warehouse,
        },
        callback: function(resp){
            if(resp.message){
                frappe.model.set_value(cdt, cdn, FieldName, resp.message);
            }
        }
    });
}

function get_subcontracting_product_mix(frm, cdt, cdn, ItemCode, FieldName){
    frm.call({
        method: 'get_subcontracting_product_mix',
        args: {
            ItemCode: ItemCode,
        },
        callback: function(resp){
            if(resp.message){
                frappe.model.set_value(cdt, cdn, FieldName, resp.message);
            }
        }
    });
}