# Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.contacts.doctype.address.address import render_address
from erpnext.stock.utils import get_stock_balance as stock_balance

def get_default_address(Doctype, Name):
	addresses = frappe.get_all(
		"Address",
		filters=[
			["Dynamic Link", "link_doctype", "=", Doctype],
			["Dynamic Link", "link_name", "=", Name],
			["disabled", "=", 0],
		],
		pluck="name",
		order_by="is_primary_address DESC",
		limit=1,
	)
	return addresses[0] if addresses else None

@frappe.whitelist()
def get_subcontracting_product_mix(ItemCode):
    return frappe.db.get_value("Subcontracting Product Mix", {'finished_item_code': ItemCode, 'disable': 0}, 'name')

@frappe.whitelist()
def get_sales_order(purchase_order):
    return frappe.get_value("Sales Order", {'custom_inter_company_po_reference': purchase_order}, 'name')

# @frappe.whitelist()
# def get_itc_rate(item_code):
# 	itc_rate = frappe.get_value("Item", item_code, 'custom_itc_rate') or 0
# 	if itc_rate == 0:
# 		frappe.msgprint(f"The Subcontracting ITC Rate Is 0 For {item_code}.")
# 	return itc_rate

def get_weight_uom(item_code):
	return frappe.get_value("Item", item_code, 'weight_uom')

def get_weight_per_unit(item_code):
	return frappe.get_value("Item", item_code, 'weight_per_unit') or 0

def get_item_name(item_code):
	return frappe.get_value("Item", item_code, 'item_name') or ''

class SubcontractingOut(Document):

	def on_submit(self):
		if self.out_type == "Purchase Order":
			self.make_stock_entry("Subcontracting Out Send to Subcontractor","subcontracting_out_po_item_details",self.company, self.target_warehouse, self.supplier_address, self.company_address)
		elif self.out_type == "Open Order":
			self.make_stock_entry("Subcontracting Out Send to Subcontractor","subcontracting_out_oo_item_details",self.company, self.target_warehouse, self.supplier_address, self.company_address)

		self.make_job_work_in()
		self.update_on_purchase_order()

	def make_job_work_in(self):
		if frappe.db.exists("Supplier", self.supplier_id,'is_internal_supplier'):
			if self.company in frappe.get_all("Allowed To Transact With", filters={'parent': self.supplier_id}, pluck='company'):
				comp = frappe.get_value("Supplier", self.supplier_id, 'represents_company')
				customer = frappe.get_value("Customer",filters={'represents_company': self.company},fieldname='name')
				job_work_in = frappe.new_doc("Job Work In")
				job_work_in.company = comp
				job_work_in.customer = customer
				job_work_in.source_warehouse = self.target_warehouse
				for po in self.purchase_order:
					sales_order = get_sales_order(po.purchase_order)
					job_work_in.append('sales_order',{
						'sales_order': sales_order
					})
				for po in self.subcontracting_out_po_item_details:
					if po.out_type:
						sales_order = get_sales_order(po.out_type)
					else:
						sales_order = ''
					jwi_warehouse = frappe.db.get_value("Job Work Settings", comp, 'job_work_in_target_warehouse')
					if not jwi_warehouse:
						frappe.throw(f"Set Job Work In Target Warehouse At Job Work Settings For {comp}")
					if po.subcontracting_operation:
						job_work_operation = frappe.db.exists("Job Work Operations",po.subcontracting_operation)
						if not job_work_operation:
							frappe.throw(f"Create {po.subcontracting_operation} Operation in Job Work Opertation")
						
					job_work_in.append('jwi_so_item_details',{
						'sales_order': sales_order,
						'item_code': po.item_code,
						'item_name': po.item_name,
						'quantity': po.quantity,
						'uom': po.uom,
						'job_work_operation': po.subcontracting_operation or '',
						'target_warehouse': jwi_warehouse,
						'rate': po.rate,
						'total_weight': get_weight_per_unit(po.item_code) * po.quantity,
						'amount': po.amount,
					})
				job_work_in.subcontracting_out = self.name
				job_work_in.save()
    
    
	def update_on_purchase_order(self):
		purchase_order = {}
		if self.out_type == "Purchase Order":
			for itm in self.get('subcontracting_out_po_item_details', {'out_type': ['!=', None]}):
				if itm.out_type in purchase_order:
					purchase_order[itm.out_type] += itm.quantity
				else:
					purchase_order[itm.out_type] = itm.quantity
		
			for po, qty in purchase_order.items():
				po_subcontracting_qty = frappe.get_value("Purchase Order", po, 'custom_subcontracting_quantity')
				frappe.db.set_value("Purchase Order", po, 'custom_subcontracting_quantity', po_subcontracting_qty + qty)

	def before_save(self):
		gst_category,gst_applicable = frappe.db.get_value('Supplier', self.supplier_id, ['gst_category','custom_gst_is_not_applicable'])
		self.subcontracting_type = "SEZ" if gst_category == "SEZ" else "Non SEZ"
		self.set_gst_itc_4_rate()
		self.validate_purchase_order()
		if not gst_applicable:
			self.get_gst_calculation()
			
	def make_stock_entry(self, type, table, company, target_warehouse, bill_from_address, bill_to_address):
		stock = frappe.new_doc("Stock Entry")
		stock.stock_entry_type = type
		stock.company = company
		stock.bill_from_address = bill_from_address
		stock.bill_to_address = bill_to_address
		for itm in self.get(table):
			stock.append('items',{
				'item_code': itm.item_code,
				'qty': itm.quantity,
				's_warehouse': itm.source_warehouse,
				't_warehouse': target_warehouse,
				'uom': itm.uom
			})
		stock.custom_subcontracting_out = self.name
		stock.insert()
		stock.submit()

	def set_gst_itc_4_rate(self):
		for out in self.get('subcontracting_out_po_item_details', filters={'quantity': ['>', 0]}):
			if out.rate <= 0 and out.item_code:
				itc_rate = frappe.get_value("Item", out.item_code, 'custom_itc_rate')
				out.rate = itc_rate
				out.amount = out.quantity * itc_rate

	def get_gst_calculation(self):
		tot_amount = 0
		tot_taxable_amount = 0
		for out in self.get('subcontracting_out_po_item_details', filters={'amount':['!=', None]}):
			tot_amount += out.amount
			item = frappe.get_doc("Item", out.item_code)
			for tax in item.taxes:
				item_tax_template = tax.item_tax_template
				company_tax_template = frappe.get_value("Item Tax Template", item_tax_template, 'company')
				
				if company_tax_template == self.company:
					out.item_tax_template = item_tax_template
					gst_rate = frappe.get_value("Item Tax Template", item_tax_template, 'gst_rate')
					out.gst_rate = gst_rate
					if self.place_of_supply == self.company_state:
						out.cgst_rate = out.sgst_rate = gst_rate / 2
						out.cgst_amount = out.sgst_amount = (out.amount / 100) * (gst_rate / 2)
					else:
						out.igst_rate = gst_rate
						out.gst_amount = (out.amount / 100) * gst_rate
					break
		for out in self.get('subcontracting_out_po_item_details'):
			tot_taxable_amount += (out.igst_amount or 0) + (out.cgst_amount or 0) + (out.sgst_amount or 0)

		if self.place_of_supply == self.company_state:
			filter ={'is_inter_state': 0, 'is_reverse_charge': 0,'gst_state': self.company_state}
			tot_taxable_amount = tot_taxable_amount / 2
		else:
			filter ={'is_inter_state': 1, 'is_reverse_charge': 0,'gst_state': self.company_state}
		
		tax_cat_list = frappe.get_value("Tax Category",filter,'name')
		self.taxes_and_charges_template = frappe.get_value("Purchase Taxes and Charges Template", {'tax_category': tax_cat_list, 'company': self.company}, 'name')
		self.subcontracting_out_taxes_and_charges.clear()
		if self.taxes_and_charges_template:
			taxes_charges_doc = frappe.get_doc("Purchase Taxes and Charges Template",{'name':self.taxes_and_charges_template})
			for tx in taxes_charges_doc.taxes:
				tot_amount += tot_taxable_amount
				self.append("subcontracting_out_taxes_and_charges",{
					"charge_type": tx.charge_type,
					"account_head": tx.account_head,
					"description": tx.description,
					"cost_center": tx.cost_center,
					"tax_amount": tot_taxable_amount,
					"total": round(tot_amount,2)
				})
		
		self.total_amount = tot_amount
		self.rounded_adjustment = tot_amount - round(tot_amount)
		self.rounded_amount = round(tot_amount)

	def validate_purchase_order(self):
		purchase_order = {}
		if self.out_type == "Purchase Order":
			for itm in self.get('subcontracting_out_po_item_details', {'out_type': ['!=', None]}):
				if itm.out_type in purchase_order:
					purchase_order[itm.out_type] += itm.quantity
				else:
					purchase_order[itm.out_type] = itm.quantity
		
			for po, qty in purchase_order.items():
				po_subcontracting_qty, po_total_qty = frappe.db.get_value("Purchase Order", po, ['custom_subcontracting_quantity', 'total_qty'])
				if po_total_qty < (po_subcontracting_qty + qty):
					frappe.throw(f"The Subcontracting Quantity Can`t Be Greater Than Purchase Order Quantity For {po} qty {po_total_qty}")

	@frappe.whitelist()
	def get_address(self, Doctype, DocName):
		ret = frappe._dict()
		if DocName:
			address_name = get_default_address(Doctype, DocName)
			if address_name:
				ret.address_display = render_address(address_name, check_permissions=False)
				return address_name, ret.address_display
			else:
				frappe.msgprint(f"Plz Set Address For {DocName}")

	@frappe.whitelist()
	def get_available_quantity(self, ItemCode, Warehouse):
		return stock_balance(ItemCode, Warehouse, self.posting_date, self.posting_time) if (self.source_warehouse and ItemCode) else 0

	@frappe.whitelist()
	def get_open_order_items_details(self, Doctype, FieldName, Table):
		child_table = self.get(Table)
		if child_table:
			child_table.clear()
		for out_type in self.get(FieldName):
			items = frappe.get_doc(Doctype, {'name':out_type.get(FieldName)})
			for itm in items.items:
				subcontracting_product_mix = get_subcontracting_product_mix(itm.get('fg_item'))
				self.append(Table,{
					'out_type': out_type.get(FieldName),
					'order_item': itm.get('item_code'),
					'item_code': itm.get('fg_item'),
					'item_name': frappe.get_value('Item', filters={'name': itm.get('fg_item')}, fieldname='item_name'),
					'quantity': itm.get('fg_item_qty'),
					'uom': itm.get('uom'),
    				'subcontracting_operation': itm.get('custom_subcontracting_operation'),
					'source_warehouse': self.get('source_warehouse'),
					'available_quantity': stock_balance(itm.get('fg_item'),self.source_warehouse,self.posting_date, self.posting_time) if (self.source_warehouse and itm.get('fg_item')) else 0,
					'rate': itm.get('rate'),
					'amount': itm.get('rate') * itm.get('fg_item_qty'),
					'subcontracting_product_mix': subcontracting_product_mix if subcontracting_product_mix else None,
					'type_of_goods': "Capital Goods" if frappe.db.get_value('Item', itm.get('fg_item'), 'is_fixed_asset') else 'Input',
				})


	@frappe.whitelist()
	def get_purchase_order_items_details(self, Doctype, FieldName, Table):
		child_table = self.get(Table)
		if child_table:
			child_table.clear()
		for out_type in self.get(FieldName):
			items = frappe.get_doc(Doctype, {'name':out_type.get(FieldName)})
			source_warhouse = self.get('source_warehouse')
			for itm in items.items:
				subcontracting_product_mix = get_subcontracting_product_mix(itm.get('custom_subcontracting_item_code'))
				item_code = itm.get('custom_subcontracting_item_code')
				# rate = get_itc_rate(item_code)
				rate = itm.get('rate')
				weight_per_unit = get_weight_per_unit(item_code)
				self.append(Table,{
					'out_type': out_type.get(FieldName),
					'order_item': itm.get('item_code'),
					'item_code': item_code,
					'item_name': get_item_name(item_code),
					'quantity': itm.get('custom_subcontracting_item_quantity'),
					'uom': get_weight_uom(item_code),
					'weight_per_unit': weight_per_unit,
					'total_weight': weight_per_unit * itm.get('custom_subcontracting_item_quantity'),
    				'subcontracting_operation': itm.get('custom_subcontracting_operation'),
					'source_warehouse': source_warhouse,
					'available_quantity': stock_balance(item_code, self.source_warehouse, self.posting_date, self.posting_time) if (self.source_warehouse and item_code) else 0,
					'rate': rate,
					'amount': rate * itm.get('custom_subcontracting_item_quantity'),
					'subcontracting_product_mix': subcontracting_product_mix if subcontracting_product_mix else None,
					'type_of_goods': "Capital Goods" if frappe.db.get_value('Item', item_code, 'is_fixed_asset') else 'Input',
					'purchase_order_item': itm.get('name')
				})

	@frappe.whitelist()
	def get_filtered_purchase_order(self):
		purchase_orders = []
		if self.supplier_id:
			purchase_orders = frappe.db.sql("""
				SELECT name FROM `tabPurchase Order` 
				WHERE supplier = %s 
				AND custom_is_subcontracting = 1 AND company = %s
				AND total_qty != custom_subcontracting_quantity AND docstatus = 1
			""", (self.supplier_id, self.company), as_dict=True)
			purchase_orders = [po['name'] for po in purchase_orders]
		return purchase_orders
