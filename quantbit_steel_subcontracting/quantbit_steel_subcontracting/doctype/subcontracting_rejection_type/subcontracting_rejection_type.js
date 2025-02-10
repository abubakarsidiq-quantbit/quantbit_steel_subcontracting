// Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Subcontracting Rejection Type", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Subcontracting Rejection Type", {
	company(frm){
        set_filters(frm, 'rejection_warehouse', 'None', [['Warehouse', 'company', '=', frm.doc.company]])
    },
});

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