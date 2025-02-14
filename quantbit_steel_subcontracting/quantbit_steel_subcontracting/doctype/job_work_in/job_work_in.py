# Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.contacts.doctype.address.address import render_address
from quantbit_steel_subcontracting.quantbit_steel_subcontracting.doctype.subcontracting_out.subcontracting_out import get_weight_per_unit

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

class JobWorkIn(Document):
	def on_submit(self):
		if self.is_opening == "No":
			self.make_stock_entry("Job Work In Receipt", 'jwi_so_item_details', self.company, self.target_warehouse)
		self.update_sales_order()

	def make_stock_entry(self, type, table, company, target_warehouse):
		stock = frappe.new_doc("Stock Entry")
		stock.stock_entry_type = type
		stock.company = company
		for itm in self.get(table):
			stock.append('items',{
				'item_code': itm.item_code,
				'qty': itm.quantity,
				't_warehouse': target_warehouse,
				'uom': itm.uom,
				'allow_zero_valuation_rate': True
			})
		stock.custom_job_work_in = self.name
		stock.insert()
		stock.submit()

	def before_save(self):
		if not self.job_work_type:
			self.job_work_type = "SEZ" if frappe.db.get_value('Customer', self.customer, 'gst_category') == "SEZ" else "Non SEZ"
		for i in self.get('jwi_so_item_details', filters={'types_of_goods': ['is', 'Not Set']}):
			i.types_of_goods = "Capital Goods" if frappe.db.get_value('Item', i.item_code, 'is_fixed_asset') else 'Input'
		self.validate_sales_order()
		gst_applicable = frappe.db.get_value('Customer', self.customer, 'custom_gst_is_not_applicable')
		if not gst_applicable:
			self.get_gst_calculation()

	def get_gst_calculation(self):
		tot_amount = 0
		tot_taxable_amount = 0
		for out in self.get('jwi_so_item_details', filters={'amount':['!=', None]}):
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
		for out in self.get('jwi_so_item_details'):
			tot_taxable_amount += (out.igst_amount or 0) + (out.cgst_amount or 0) + (out.sgst_amount or 0)

		if self.place_of_supply == self.company_state:
			filter ={'is_inter_state': 0, 'is_reverse_charge': 0,'gst_state': self.company_state}
			tot_taxable_amount = tot_taxable_amount / 2
		else:
			filter ={'is_inter_state': 1, 'is_reverse_charge': 0,'gst_state': self.company_state}

		tax_cat_list = frappe.get_value("Tax Category",filter,'name')
		self.taxes_and_charges_template = frappe.get_value("Sales Taxes and Charges Template", {'tax_category': tax_cat_list, 'company': self.company}, 'name')
		self.job_work_in_taxes_and_charges.clear()
		if self.taxes_and_charges_template:
			taxes_charges_doc = frappe.get_doc("Sales Taxes and Charges Template",{'name':self.taxes_and_charges_template})
			for tx in taxes_charges_doc.taxes:
				tot_amount += tot_taxable_amount
				self.append("job_work_in_taxes_and_charges",{
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
	def get_out_type_items_details(self, Doctype, FieldName, Table):
		child_table = self.get(Table)
		if child_table:
			child_table.clear()
		for out_type in self.get(FieldName):
			items = frappe.get_doc(Doctype, {'name':out_type.get(FieldName)})
			for itm in items.items:
				job_work_item = itm.get('custom_job_work_item_code')
				weight_per_unit = get_weight_per_unit(job_work_item)
				self.append(Table,{
					'sales_order': out_type.get(FieldName),
					'item_code': job_work_item,
					'item_name': itm.get('custom_job_work_item_name'),
					'quantity': itm.get('custom_job_work_item_qty'),
					'uom': frappe.get_value('Item', filters={'name': job_work_item}, fieldname='stock_uom'),
    				'job_work_operation': itm.get('custom_subcontracting_operation'),
					'target_warehouse': self.get('target_warehouse'),
					'rate': itm.get('rate'),
					'amount': itm.get('rate') * itm.get('custom_job_work_item_qty'),
					'total_weight': weight_per_unit * itm.get('custom_job_work_item_qty'),
					'types_of_goods': "Capital Goods" if frappe.db.get_value('Item', job_work_item, 'is_fixed_asset') else 'Input',
				})

	def validate_sales_order(self):
		sales_order = {}
		for itm in self.get('jwi_so_item_details', {'sales_order': ['!=', None]}):
			if itm.sales_order in sales_order:
				sales_order[itm.sales_order] += itm.quantity
			else:
				sales_order[itm.sales_order] = itm.quantity
	
		for so, qty in sales_order.items():
			if so:
				so_job_work_qty, so_total_qty = frappe.db.get_value("Sales Order", so, ['custom_total_job_work_quantity', 'total_qty'])
				if so_total_qty < (so_job_work_qty + qty):
					frappe.throw(f"The Job Work Quantity Can`t Be Greater Than Sales Order Quantity For {so}")

	def update_sales_order(self):
		sales_order = {}
		for itm in self.get('jwi_so_item_details', {'sales_order': ['!=', None]}):
			if itm.sales_order in sales_order:
				sales_order[itm.sales_order] += itm.quantity
			else:
				sales_order[itm.sales_order] = itm.quantity
	
		for so, qty in sales_order.items():
			if so:
				so_job_work_qty = frappe.get_value("Sales Order", so, 'custom_total_job_work_quantity')
				frappe.db.set_value("Sales Order", so, 'custom_total_job_work_quantity', so_job_work_qty + qty)

	@frappe.whitelist()
	def get_filtered_sales_order(self):
		sales_orders = []
		if self.customer:
			sales_orders = frappe.db.sql("""
				SELECT name FROM `tabSales Order` 
				WHERE customer = %s 
				AND custom_is_job_work = 1 AND company =  %s
				AND total_qty != custom_total_job_work_quantity AND docstatus = 1
			""", (self.customer, self.company), as_dict=True)
			sales_orders = [so['name'] for so in sales_orders]
		return sales_orders