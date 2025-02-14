# Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.contacts.doctype.address.address import render_address
from erpnext.stock.utils import get_stock_balance


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

def get_item_name(item):
	return frappe.db.get_value("Item", item, 'item_name')

def get_default_uom(item):
	return frappe.db.get_value("Item", item, 'weight_uom')

def get_weight_per_unit(item):
	return frappe.db.get_value("Item", item, 'weight_per_unit') or frappe.throw(f"Set Weight Per Unit Value For {item}")

def calculate_raw_per_weight(item_code, weight_per_unit, percentage):
	return ((weight_per_unit / 100) * percentage) / get_weight_per_unit(item_code)

class JobWorkOut(Document):
	def set_type_of_goods(self):
		for fg in self.job_work_out_finished_item_details:
			fg.types_of_goods = "Capital Goods" if frappe.db.get_value('Item', fg.item_code, 'is_fixed_asset') else 'Input'

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
			
	def get_grade_for_foundry(self):
		grades = set()
		for finished in self.get('job_work_out_finished_item_details'):
			grade = frappe.get_value('Item', finished.item_code, 'custom_grade')
			if grade:
				grades.add(grade)
		return grades

	def get_raw_items(self):
		grades = self.get_grade_for_foundry()
		raw_item = frappe.db.sql("""
			SELECT item_code
			FROM `tabGrade Items Details` AS m
			JOIN `tabGrade Master` g ON m.parent = g.name
			WHERE g.name IN %(grades)s
		""", {"grades": tuple(grades)}, as_list=True)
		return [item for sublist in raw_item for item in sublist]

	def append_challan_data_to_table(self, in_challan):
		for in_ch in in_challan:
			self.append('job_work_in_item_details', {
				'job_work_in_challan_date': in_ch['posting_date'],
				'jw_in_challan': in_ch['name'],
				'sales_order': in_ch['sales_order'],
				'item_code': in_ch['item_code'],
				'item_name': in_ch['item_name'],
				'uom': in_ch['uom'],
				'weight_per_unit': in_ch['weight_per_unit'],
				'job_work_operation': in_ch['job_work_operation'],
				'job_work_in_quantity': in_ch['quantity'],
				'available_quantity': get_stock_balance(in_ch['item_code'], self.source_warehouse, self.posting_date),
				'returned_quantity': in_ch['returned_quantity'],
				'refrence': in_ch['ref']
			})
			item = self.get('job_work_out_raw_items_details', {'item_code': in_ch['item_code']})
			if not item:
				self.append('job_work_out_raw_items_details', {
					'item_code': in_ch['item_code'],
					'item_name': in_ch['item_name'],
					'uom': in_ch['uom'],
					'weight_per_unit': in_ch['weight_per_unit']
				})

	@frappe.whitelist()
	def get_job_work_in_challan_for_above_items(self):
		self.job_work_in_item_details.clear()
		self.job_work_out_raw_items_details.clear()
		self.job_work_out_rejection_reason.clear()

		if not self.job_work_out_from:
			frappe.throw("Select Job Work Out From Foundry/Machining")

		if not (self.customer and self.source_warehouse):
			frappe.throw("Select customer and source warehouse")

		raw_items = set()
		if self.job_work_out_from == "Foundry" and self.customer and self.source_warehouse:
			raw_items = self.get_raw_items()
			error_message = "Please check finished item is set or Pattern Master is created for these items."
		elif self.job_work_out_from == "Machining" and self.customer and self.source_warehouse:
			for fg in self.get('job_work_out_finished_item_details'):
				rw_item = frappe.get_value("MachineShop Processflow", {'finished_item_code': fg.item_code}, 'raw_item')
				if rw_item:
					raw_items.add(rw_item)
			error_message = "Please check finished item is set or finished item MachineShop Processflow is designed."
	
		if not raw_items:
			frappe.throw(error_message)

		in_challan = self.get_job_work_in_data(raw_items)
		if in_challan:
			self.append_challan_data_to_table(in_challan)
		else:
			frappe.throw(title="No Job Work In", msg = "No Job Work In is done for selected finished item`s raw item.")

	def get_job_work_in_data(self, raw_items):
		"""--------------------------Function to fetch Job Work In challan data.---------------------------"""
		return frappe.db.sql("""
			SELECT jwi.name, jwi.posting_date, jwiso.item_code, jwiso.item_name, jwiso.quantity, jwiso.job_work_operation, 
				jwiso.returned_quantity, jwiso.uom, jwiso.sales_order, jwiso.weight_per_unit, jwiso.name as ref
			FROM `tabJob Work In` as jwi 
			LEFT JOIN `tabJob Work In Sales Order Item Details` jwiso ON jwi.name = jwiso.parent
			WHERE jwiso.item_code IN %(raw_items)s AND jwiso.quantity > jwiso.returned_quantity 
			AND jwi.docstatus = 1 AND jwi.customer = %(customer)s AND jwi.job_work_for = %(job_work_out_from)s 
			AND jwi.company = %(company)s
		""", {"raw_items": tuple(raw_items),"customer": self.customer,"job_work_out_from": self.job_work_out_from,"company": self.company}, as_dict=True)

	def on_submit(self):
		for i in self.job_work_out_bifurcation_details:
			returned_quantity = frappe.db.get_value("Job Work In Sales Order Item Details", {'name': i.reference_id}, 'returned_quantity')
			frappe.db.set_value("Job Work In Sales Order Item Details", {'name': i.reference_id}, 'returned_quantity', returned_quantity + i.quantity)
		if frappe.get_value("Customer", self.customer,'is_internal_customer'):
			if self.company in frappe.get_all("Allowed To Transact With", filters={'parent': self.customer}, pluck='company'):
				comp = frappe.get_value("Customer", self.customer, 'represents_company')
				supplier = frappe.get_value("Supplier",filters={'represents_company': self.company},fieldname='name')
				sub_in = frappe.new_doc("Subcontracting In")
				sub_in.company = comp
				sub_in.supplier_id = supplier
				subcontracting_setting = frappe.get_doc("Subcontracting Settings", comp)
				if subcontracting_setting.account:
					sub_in.account = subcontracting_setting.account
					sub_in.description = subcontracting_setting.description
				else:
					frappe.throw("Set Account and Description in Subcontracting Settings for Additional Cost")
				sub_in.save()

		self.make_without_sales_order_delivery_challan()
		self.make_with_sales_order_delivery_challan()

	def make_with_sales_order_delivery_challan(self):
		sales_order = []
		del_note = frappe.new_doc("Delivery Note")
		del_note.customer = self.customer
		del_note.company = self.company
		del_note.set_warehouse = self.source_warehouse
		del_note.set_target_warehouse = self.target_warehouse

		for itm in self.job_work_out_bifurcation_details:
			if itm.sales_order and itm.sales_order not in sales_order:
				sales_order.append(itm.sales_order)
				sales_order_item = frappe.db.get_values(
					"Sales Order Item",
					{'parent': itm.sales_order, 'custom_job_work_item_code': itm.item_code},
					['item_code', 'name', 'qty', 'rate'],
					as_dict=True
				)

				if sales_order_item:
					item_code = sales_order_item[0].item_code
					so_detail = sales_order_item[0].name
					qty = itm.quantity
					rate = sales_order_item[0].rate
				else:
					frappe.throw(f"No matching Sales Order Item found for Sales Order: {itm.sales_order} and Item Code: {itm.item_code}")

				del_note.append('items', {
					'item_code': item_code,
					'against_sales_order': itm.sales_order,
					'so_detail': so_detail,
					'qty': qty,
					'rate': rate,
				})
		if sales_order:
			del_note.custom_job_work_out = self.name
			del_note.save()
			del_note.submit()

	def make_without_sales_order_delivery_challan(self):
		del_note = frappe.new_doc("Delivery Note")
		del_note.customer = self.customer
		del_note.company = self.company
		del_note.set_warehouse = self.source_warehouse
		del_note.set_target_warehouse = self.target_warehouse
		for i in self.job_work_out_bifurcation_details:
			del_note.append('items',{
				'item_code': i.item_code,
				'warehouse': self.source_warehouse,
				'target_warehouse': self.target_warehouse,
				'qty': i.quantity,
				'rate': frappe.get_value("Item", i.item_code, 'custom_itc_rate') or 0,
			})
		del_note.custom_job_work_out = self.name
		del_note.save()
		del_note.submit()

	def on_cancel(self):
		for i in self.job_work_out_bifurcation_details:
			returned_quantity = frappe.db.get_value("Job Work In Sales Order Item Details", {'parent': i.job_work_in_challan, 'item_code': i.item_code}, 'returned_quantity')
			frappe.db.set_value("Job Work In Sales Order Item Details", {'parent': i.job_work_in_challan, 'item_code': i.item_code}, 'returned_quantity', returned_quantity - i.quantity)
	
	def validate(self):
		if not self.job_work_type:
			self.job_work_type = "SEZ" if frappe.db.get_value('Customer', self.customer, 'gst_category') == "SEZ" else "Non SEZ"
		self.set_type_of_goods()
		required_items = self.validate_required_item_qty_than_checked_items_qty()
		self.get_challan_wise_raw_material_bifurgation(required_items)

	def get_required_items(self, required_items, child_table, filters, field):
		for raw in self.get(child_table, filters):
			if raw.item_code in required_items:
				required_items[raw.item_code] += raw.get(field)
			else:
				required_items[raw.item_code] = raw.get(field)

	def validate_required_item_qty_than_checked_items_qty(self):
		required_items, available_items = {}, {}
		self.get_required_items(required_items, 'job_work_out_raw_item_details', {'required_quantity': ['>', 0]}, 'required_quantity')
		self.get_required_items(required_items, 'job_work_out_rejection_reason', {'rejection_quantity': ['>', 0]}, 'rejection_quantity')
		self.get_required_items(required_items, 'job_work_out_raw_items_details', {'as_it_is_qty': ['>', 0]}, 'as_it_is_qty')

		for available in self.get('job_work_in_item_details', {'check': 1}):
			if available.item_code in available_items:
				available_items[available.item_code] += (available.job_work_in_quantity - available.returned_quantity)
			else:
				available_items[available.item_code] = (available.job_work_in_quantity - available.returned_quantity)

		for itm, qty in required_items.items():
			if itm in available_items:
				if qty > available_items[itm]:
					frappe.throw(f"The total required qty is more than check challan qty for {itm}")
			else:
				frappe.throw(f"The {itm} is not check")
		return required_items
	
	def get_challan_wise_raw_material_bifurgation(self, required_items):
		self.job_work_out_bifurcation_details.clear()
		
		reference_details = {
			d['name']: d for d in frappe.get_all("Job Work In Sales Order Item Details", 
				filters={'name': ['in', [check.refrence for check in self.get('job_work_in_item_details', filters={'check': 1})]]},
				fields=['name', 'quantity', 'returned_quantity']
			)
		}

		for check in self.get('job_work_in_item_details', filters={'check': 1}):
			ref_details = reference_details.get(check.refrence)
			if not ref_details:
				continue
			available_quantity = ref_details['quantity'] - ref_details['returned_quantity']
			required_qty = required_items[check.item_code]
			allocation_qty = min(required_qty, available_quantity)
			self.append('job_work_out_bifurcation_details', {
				'job_work_in_challan': check.jw_in_challan,
				'item_code': check.item_code,
				'item_name': check.item_name,
				'job_work_in_quantity': check.job_work_in_quantity,
				'returned_quantity': check.returned_quantity,
				'sales_order': check.sales_order,
				'jw_operation': check.job_work_operation,
				'reference_id': check.refrence,
				'types_of_goods': "Capital Goods" if frappe.db.get_value('Item', check.item_code, 'is_fixed_asset') else 'Input',
				'quantity': allocation_qty
			})
			required_items[check.item_code] -= allocation_qty
						
	@frappe.whitelist()
	def get_required_raw_item_of_finished_ok_qty(self):
		raw_items = {}
		if self.job_work_out_from == "Foundry":
			self.job_work_out_raw_item_details.clear()
			for fg in self.get('job_work_out_finished_item_details', filters={'ok_qty': ['>', 0]}):
				grade = frappe.get_value("Item", fg.item_code, 'custom_grade')
				if grade:
					raw_item = frappe.db.sql("""
						SELECT item_code, percentage
						FROM `tabGrade Items Details` AS m
						JOIN `tabGrade Master` g ON m.parent = g.name
						WHERE g.name = %s
					""", {grade}, as_dict=True)
					for rw in raw_item:
						if rw.item_code in raw_items:
							raw_items[rw.item_code] += fg.ok_qty * (rw.percentage / 100)
						else:
							raw_items[rw.item_code] = fg.ok_qty * (rw.percentage / 100)

		elif self.job_work_out_from == "Machining":
			self.job_work_out_raw_item_details.clear()
			for fg in self.get('job_work_out_finished_item_details', filters={'ok_qty': ['>', 0]}):
				rw_item = frappe.get_value("MachineShop Processflow", {'finished_item_code': fg.item_code}, 'raw_item')
				if rw_item:
					if rw_item in raw_items:
						raw_items[rw_item] += fg.ok_qty
					else:
						raw_items[rw_item] = fg.ok_qty

		else:
			frappe.throw("Select Job Work Out From Foundry/Machining")
		for itm, qty in raw_items.items():
			self.append('job_work_out_raw_item_details', {
				'item_code': itm,
				'required_quantity': qty
			})

	@frappe.whitelist()
	def get_rejection_reason_for_rejected_qty(self, item, qty, field):
		rejection_exist = False
		rejection_type = frappe.get_value('Subcontracting Rejection Type', {'subcontracting_field': field}, 'name')
		for rej in self.get('job_work_out_rejection_reason', filters={'item_code': item, 'rejection_type': rejection_type}):
			rej.rejection_quantity = qty
			rejection_exist = True
			break
		if not rejection_exist:
			self.append('job_work_out_rejection_reason', {
				'item_code': item,
				'rejection_type': rejection_type,
				'rejection_quantity': qty
			})
 
	@frappe.whitelist()
	def get_rejection_bifurgation(self, item, rej):
		tot_qty = 0
		record = self.get('job_work_out_finished_item_details', filters={'item_code': item})
		if record:
			rejection_details = self.get('job_work_out_rejection_reason', filters={'item_code': item, 'rejection_type': rej})
			for q in rejection_details:
				tot_qty += q.rejection_quantity
			field_name = f'{rej.lower()}_qty'
			available_qty = record[0].get(field_name, 0)
			if tot_qty > available_qty:
				frappe.throw(f"Rejection quantity for item '{item}' and type '{rej}' cannot be greater than the available quantity ({available_qty}) in Subcontracting In Finished Item Details.")
			
			remaining_qty = available_qty - tot_qty
			if remaining_qty > 0:
				self.append('job_work_out_rejection_reason', {
					'item_code': item,
					'rejection_type': rej,
					'rejection_quantity': remaining_qty
				})