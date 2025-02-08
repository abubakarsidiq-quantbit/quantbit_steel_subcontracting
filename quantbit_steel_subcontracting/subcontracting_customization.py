import frappe
from quantbit_steel_subcontracting.quantbit_steel_subcontracting.doctype.subcontracting_out.subcontracting_out import get_weight_uom, get_weight_per_unit, get_item_name

def get_item_group(item_code):
    return frappe.get_value("Item", item_code, 'item_group')

@frappe.whitelist()
def create_sales_order_from_po_for_is_internal_supplier(doc):
    purchase_order = frappe.get_doc("Purchase Order", doc)
    sales_order = frappe.new_doc("Sales Order")
    customer = frappe.get_value("Customer",filters={'represents_company': purchase_order.company},fieldname='name')
    company = frappe.get_value("Supplier", purchase_order.supplier, 'represents_company')
    if not company:
        frappe.throw("This supplier does not represents any company.")
    if not customer:
        frappe.throw(f"There is no customer that represents {purchase_order.company}.So sales order will not generate.")
    sales_order.customer = customer
    sales_order.company = company
    sales_order.selling_price_list = purchase_order.buying_price_list
    sales_order.delivery_date = purchase_order.schedule_date
    sales_order.custom_is_job_work = 1
    for itm in purchase_order.items:
        if itm.custom_subcontracting_operation:
            custom_subcontracting_operation = frappe.get_value("Job Work Operations", itm.custom_subcontracting_operation, 'name')
            if not custom_subcontracting_operation:
                frappe.throw(f"Create {itm.custom_subcontracting_operation} Operation in Job Work Opertation")
        else:
            custom_subcontracting_operation = ''
        job_work_item = itm.custom_subcontracting_item_code
        weight_per_unit = get_weight_per_unit(job_work_item)
        sales_order.append('items',{
            'item_code': itm.item_code,
            'item_name': itm.item_name,
            'uom': itm.uom,
            'qty': itm.qty,
            'rate': itm.rate,
            'amount': itm.amount,
            'delivery_date': itm.schedule_date,
            'custom_job_work_item_code': job_work_item,
            'custom_job_work_item_name': get_item_name(job_work_item),
            'custom_job_work_item_group': get_item_group(job_work_item),
            'custom_subcontracting_operation': custom_subcontracting_operation or '',
            'custom_job_work_item_qty': itm.custom_subcontracting_item_quantity,
            'custom_job_work_item_weight_uom': get_weight_uom(job_work_item),
            'custom_job_work_item_weight_per_unit': weight_per_unit,
            'custom_job_work_item_total_weight': weight_per_unit * itm.custom_subcontracting_item_quantity,
            'custom_inter_company_po_reference': purchase_order.name,
        })
    sales_order.custom_inter_company_po_reference = purchase_order.name
    sales_order.save()
    frappe.msgprint(f"Sales Order Generated. The Sales Order Id Is {sales_order.name}")
    



@frappe.whitelist()
def create_purchase_order_from_so_for_is_internal_supplier(doc):
    sales_order = frappe.get_doc("Sales Order", doc)
    purchase_order = frappe.new_doc("Purchase Order")
    
    supplier = frappe.get_value("Supplier", filters={'represents_company': sales_order.company}, fieldname='name')
    company = frappe.get_value("Customer", sales_order.customer, 'represents_company')
    
    if not company:
        frappe.throw(f"This customer does not represent any company, unable to create PO for {sales_order.company}.")
    
    if not supplier:
        frappe.throw(f"There is no supplier that represents {sales_order.company}. So Purchase Order will not be generated.")
    
    purchase_order.supplier = supplier
    purchase_order.company = company
    purchase_order.schedule_date = sales_order.delivery_date
    purchase_order.custom_is_subcontracting = 1
    purchase_order.buying_price_list = sales_order.selling_price_list

    for itm in sales_order.items:
        if itm.custom_subcontracting_operation:
            custom_subcontracting_operation = frappe.get_value("Job Work Operations", itm.custom_subcontracting_operation, 'name')
            if not custom_subcontracting_operation:
                frappe.throw(f"Create {itm.custom_subcontracting_operation} Operation in Job Work Operation")
        else:
            custom_subcontracting_operation = ''
        job_work_item = itm.custom_job_work_item_code
        weight_per_unit = get_weight_per_unit(job_work_item)
        purchase_order.append('items', {
            'item_code': itm.item_code,
            'item_name': itm.item_name,
            'uom': itm.uom,
            'qty': itm.qty,
            'rate': itm.rate,
            'amount': itm.amount,
            'schedule_date': itm.delivery_date,
            'custom_subcontracting_operation': custom_subcontracting_operation,
            'custom_subcontracting_item_code': job_work_item,
            'custom_subcontracting_item_name': get_item_name(job_work_item),
            'custom_subcontracting_item_group': get_item_group(job_work_item),
            'custom_subcontracting_item_quantity': itm.custom_job_work_item_qty,
            'custom_subcontracting_item_weight_uom': get_weight_uom(job_work_item),
            'custom_subcontracting_item_weight_per_unit': weight_per_unit,
            'custom_subcontracting_item_total_weight': weight_per_unit * itm.custom_job_work_item_qty,
            # 'custom_inter_company_so_reference': sales_order.name
        })

    # purchase_order.custom_inter_company_so_reference = sales_order.name
    purchase_order.save()
    for itm in sales_order.items:
        frappe.db.set_value("Sales Order Item", itm.name, 'custom_inter_company_po_reference', purchase_order.name)
    frappe.db.set_value("Sales Order", sales_order.name, 'custom_inter_company_po_reference', purchase_order.name)
    frappe.msgprint(f"Purchase Order Generated. The Purchase Order Id is {purchase_order.name}")