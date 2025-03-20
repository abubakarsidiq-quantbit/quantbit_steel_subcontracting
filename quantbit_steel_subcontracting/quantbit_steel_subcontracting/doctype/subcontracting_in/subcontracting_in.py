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

class SubcontractingIn(Document):
	def on_cancel(self):
		for i in self.subcontracting_in_bifurcation_details:
			if i.purchase_order:
				returned_quantity = frappe.db.get_value("Subcontracting Out Purchase Order Item Details", {'parent': i.subcontracting_out_challan, 'item_code': i.item_code, 'out_type': i.purchase_order}, 'returned_quantity')
				frappe.db.set_value("Subcontracting Out Purchase Order Item Details", {'parent': i.subcontracting_out_challan, 'item_code': i.item_code, 'out_type': i.purchase_order}, 'returned_quantity', returned_quantity - i.quantity)
			else:
				returned_quantity = frappe.get_value("Subcontracting Out Open Order Item Details", {'parent': i.subcontracting_out_challan, 'item_code': i.item_code}, 'returned_quantity')
				frappe.db.set_value("Subcontracting Out Purchase Order Item Details", {'parent': i.subcontracting_out_challan, 'item_code': i.item_code}, 'returned_quantity', returned_quantity - i.quantity)

	
	@frappe.whitelist()
	def get_address(self, Doctype, DocName):
		ret = frappe._dict()
		if DocName:
			address_name = get_default_address(Doctype, DocName)
			if address_name:
				self.place_of_supply = frappe.get_value("Address", address_name, 'state')
				ret.address_display = render_address(address_name, check_permissions=False)
				return address_name, ret.address_display
			else:
				frappe.msgprint(f"Plz Set Address For {DocName}")

	def on_submit(self):
		if len(self.subcontracting_in_bifurcation_details) == 0:
			frappe.throw("You Can`t Submit With Zero(0) Quantity")
		checked_out_item, in_item_qty = self.validate_outgoing_and_incoming_qty()
		self.get_bifurcation_details_data(checked_out_item, in_item_qty)
		self.make_material_transfer_stock_entry("Subcontracting In Transfer", 'subcontracting_in_finished_item_details', self.company, self.target_warehouse)
		self.make_manufacture_stock_entry("Subcontracting In Manufacture", 'subcontracting_in_finished_item_details', self.company, self.target_warehouse)
		self.close_out_challan_qty()

	def before_save(self):
		gst_category = frappe.db.get_value('Supplier', self.supplier_id, 'gst_category')
		self.subcontracting_type = "SEZ" if gst_category == "SEZ" else "Non SEZ"
		checked_out_item, in_item_qty = self.validate_outgoing_and_incoming_qty()
		self.get_bifurcation_details_data(checked_out_item, in_item_qty)
		self.get_total_weight_subcon_weight()
  
	def make_material_transfer_stock_entry(self, type, table, company, target_warehouse):
		stock = frappe.new_doc("Stock Entry")
		stock.stock_entry_type = type
		stock.company = company
		flag = False
		rejection_types = frappe.get_all("Subcontracting Rejection Type", {'company': company}, ['subcontracting_field','is_as_it_is'])
		for itm in self.get(table):
			for rejection in rejection_types:
				rejection_field = rejection.get('subcontracting_field')
				is_as_it_is = rejection.get('is_as_it_is')
				qty = getattr(itm, rejection_field, 0)
				if qty > 0:
					flag = True
					if is_as_it_is == 0:
						target_warehouse = frappe.get_value('Subcontracting Rejection Type',filters={'subcontracting_field': rejection_field, 'company': company}, fieldname='rejection_warehouse')
					stock.append('items', {
						'item_code': itm.item_code,
						'qty': qty,
						's_warehouse': self.source_warehouse,
						't_warehouse': target_warehouse,
						'uom': itm.uom
					})
		if flag:
			stock.custom_subcontracting_in = self.name
			stock.insert()
			stock.submit()

	def make_manufacture_stock_entry(self, type, table, company, target_warehouse):
		for itm in self.get(table):
			stock = frappe.new_doc("Stock Entry")
			stock.stock_entry_type = type
			stock.company = company
			if itm.ok_qty > 0 and itm.is_subcontracting_product_mix:
				product_mix_items = frappe.get_all('Subcontracting Product Mix Raw Material Details', filters={'parent': itm.subcontracting_product_mix}, fields=['item_code', 'quantity', 'default_uom'])
				product_mix_quantity = frappe.get_value('Subcontracting Product Mix', {'name': itm.subcontracting_product_mix}, 'quantity')
				
				stock.append('items', {
					'item_code': itm.item_code,
					'qty': itm.ok_qty,
					't_warehouse': target_warehouse,
					'uom': itm.uom,
					'is_finished_item': 1
				})
				
				average_amount_for_twice_po = self.get('subcontracting_in_bifurcation_details', filters={'item_code': itm.item_code, 'rate': ['!=', 0]})
				for po in average_amount_for_twice_po:
					rate = frappe.get_value("Subcontracting Out Purchase Order Item Details",
						filters={'parent': po.subcontracting_out_challan,'item_code': itm.item_code,'out_type': po.purchase_order,'subcontracting_operation': po.subcontracting_operation},
						fieldname='rate')
					if rate:
						amount = itm.ok_qty * rate
					else:
						rate = frappe.get_value("Subcontracting Out Purchase Order Item Details",
							filters={'parent': po.subcontracting_out_challan,'item_code': itm.item_code,'subcontracting_operation': po.subcontracting_operation},
							fieldname='rate')
						if rate:
							amount = itm.ok_qty * rate * (frappe.get_value("Item", itm.item_code, 'weight_per_unit'))
						else:
							amount = 0

				if amount > 0:
					stock.append('additional_costs', {
						'expense_account': self.account,
						'description': self.description,
						'amount': amount
					})

				for rw_item in product_mix_items:
					stock.append('items', {
						'item_code': rw_item['item_code'],
						'qty': (rw_item['quantity'] / product_mix_quantity) * itm.ok_qty,
						's_warehouse': self.source_warehouse,
						'uom': rw_item['default_uom']
					})
				stock.custom_subcontracting_in = self.name
				stock.insert()
				stock.submit()
			else:
				if itm.ok_qty:
					stock = frappe.new_doc("Stock Entry")
					stock.stock_entry_type = type
					stock.company = company
					average_amount_for_twice_po = self.get('subcontracting_in_bifurcation_details', filters={'item_code': itm.item_code})
					
					average_amount_for_twice_po = self.get('subcontracting_in_bifurcation_details', filters={'item_code': itm.item_code, 'rate': ['!=', 0]})
					for po in average_amount_for_twice_po:
						rate = frappe.get_value("Subcontracting Out Purchase Order Item Details",
							filters={'parent': po.subcontracting_out_challan,'item_code': itm.item_code,'out_type': po.purchase_order,'subcontracting_operation': po.subcontracting_operation},
							fieldname='rate')
						if rate:
							amount = itm.ok_qty * rate
						else:
							rate = frappe.get_value("Subcontracting Out Purchase Order Item Details",
								filters={'parent': po.subcontracting_out_challan,'item_code': itm.item_code,'subcontracting_operation': po.subcontracting_operation},
								fieldname='rate')
							if rate:
								amount = itm.ok_qty * rate * (frappe.get_value("Item", itm.item_code, 'weight_per_unit'))
							else:
								amount = 0

					if amount > 0:
						stock.append('additional_costs', {
							'expense_account': self.account,
							'description': self.description,
							'amount': amount
						})
					
					stock.append('items', {
						'item_code': itm.item_code,
						'qty': itm.ok_qty,
						's_warehouse': self.source_warehouse,
						'uom': itm.uom,
					})
					stock.append('items', {
						'item_code': itm.item_code,
						'qty': itm.ok_qty,
						't_warehouse': target_warehouse,
						'uom': itm.uom,
						'is_finished_item': 1
					})
					stock.custom_subcontracting_in = self.name
					stock.save()
					stock.submit()

	@frappe.whitelist()
	def get_rejection_bifurgation(self, item, rej, qty):
		tot_qty = 0
		record = self.get('subcontracting_in_finished_item_details', filters={'item_code': item})
		if record:
			rejection_details = self.get('subcontracting_in_rejection_reason', filters={'item_code': item, 'rejection_type': rej})
			for q in rejection_details:
				tot_qty += q.rejection_quantity
			field_name = f'{rej.lower()}_qty'
			available_qty = record[0].get(field_name, 0)
			if tot_qty > available_qty:
				frappe.throw(f"Rejection quantity for item '{item}' and type '{rej}' cannot be greater than the available quantity ({available_qty}) in Subcontracting In Finished Item Details.")
			
			remaining_qty = available_qty - tot_qty
			if remaining_qty > 0:
				self.append('subcontracting_in_rejection_reason', {
					'item_code': item,
					'rejection_type': rej,
					'rejection_quantity': remaining_qty
				})

  
	def validate_outgoing_and_incoming_qty(self):
		in_item_qty = {}
		checked_item_qty = {}

		for checked_item in self.subcontracting_out_item_details:
			if checked_item.check:
				qty = checked_item.subcontracting_out_quantity - checked_item.returned_quantity
				if checked_item.item_code in checked_item_qty:
					checked_item_qty[checked_item.item_code] += qty
				else:
					checked_item_qty[checked_item.item_code] = qty

		for in_item in self.subcontracting_in_finished_item_details:
			in_quantity = (in_item.ok_qty + in_item.cr_qty + in_item.mr_qty + in_item.rw_qty + in_item.as_it_is_qty)

			if in_item.is_subcontracting_product_mix:
				product_mix_quantity = frappe.get_value('Subcontracting Product Mix', {'name': in_item.subcontracting_product_mix}, 'quantity')
				product_mix_items = frappe.get_all('Subcontracting Product Mix Raw Material Details', filters={'parent': in_item.subcontracting_product_mix}, fields=['item_code', 'quantity'])
				for raw_item in product_mix_items:
					raw_item_qty = (raw_item['quantity'] / product_mix_quantity) * in_item.ok_qty
					if raw_item['item_code'] in in_item_qty:
						in_item_qty[raw_item['item_code']] += raw_item_qty
					else:
						in_item_qty[raw_item['item_code']] = raw_item_qty

				if in_item.item_code in in_item_qty:
					in_item_qty[in_item.item_code] += (in_item.cr_qty + in_item.mr_qty + in_item.rw_qty + in_item.as_it_is_qty)
				else:
					in_item_qty[in_item.item_code] = (in_item.cr_qty + in_item.mr_qty + in_item.rw_qty + in_item.as_it_is_qty)
			else:
				if in_item.item_code in in_item_qty:
					in_item_qty[in_item.item_code] += in_quantity
				else:
					in_item_qty[in_item.item_code] = in_quantity

		for item_code, qty in in_item_qty.items():
			outgoing_qty = checked_item_qty.get(item_code, 0)
			if qty > outgoing_qty:
				frappe.throw(f"The total incoming quantity for item {item_code} ({qty}) cannot exceed the outgoing quantity ({outgoing_qty}).")

		return checked_item_qty, in_item_qty

  
	def get_bifurcation_details_data(self, checked_out_item, in_item_qty):
		self.subcontracting_in_bifurcation_details.clear()
		for checked_item in self.get('subcontracting_out_item_details', filters={'check': 1}):
			remaining_qty = checked_item.subcontracting_out_quantity - checked_item.returned_quantity
			if in_item_qty.get(checked_item.item_code, 0) > remaining_qty:
				quantity = remaining_qty
				in_item_qty[checked_item.item_code] -= quantity
			elif in_item_qty.get(checked_item.item_code, 0) <= remaining_qty:
				quantity = in_item_qty[checked_item.item_code]
				in_item_qty[checked_item.item_code] = 0
			else:
				frappe.throw(f"You are exceeding the challan quantity for item ({checked_item.item_code})")

			if quantity > 0:
				self.append('subcontracting_in_bifurcation_details', {
					'subcontracting_out_challan': checked_item.subcontracting_out_challan,
					'item_code': checked_item.item_code,
					'subcontracting_out_quantity': checked_item.subcontracting_out_quantity,
					'returned_quantity': checked_item.returned_quantity,
					'quantity': quantity,
					'purchase_order': checked_item.purchase_order,
					'subcontracting_operation': checked_item.subcontracting_operation
				})

	def close_out_challan_qty(self):
		for out_challan in self.get('subcontracting_in_bifurcation_details'):
			if out_challan.purchase_order:
				out = frappe.get_all("Subcontracting Out Purchase Order Item Details", 
					filters={'parent': out_challan.subcontracting_out_challan, 'item_code': out_challan.item_code, 'out_type': out_challan.purchase_order})
			else:
				out = frappe.get_all("Subcontracting Out Purchase Order Item Details", 
									filters={'parent': out_challan.subcontracting_out_challan, 'item_code': out_challan.item_code})

			if not out:
				out = frappe.get_all("Subcontracting Out Open Order Item Details", 
									filters={'parent': out_challan.subcontracting_out_challan, 'item_code': out_challan.item_code})
				if not out:
					frappe.throw(f"No matching details found for Subcontracting Out Challan {out_challan.subcontracting_out_challan} and item {out_challan.item_code}")

				doc_type = "Subcontracting Out Open Order Item Details"
			else:
				doc_type = "Subcontracting Out Purchase Order Item Details"
			
			out_doc = frappe.get_doc(doc_type, out[0].name)
			frappe.db.set_value(doc_type, out[0].name, 'returned_quantity', out_doc.returned_quantity + out_challan.quantity)
		
	@frappe.whitelist()
	def get_account_and_description(self):
		subcontracting_setting = frappe.get_doc("Subcontracting Settings", self.company)
		if subcontracting_setting.account:
			self.account = subcontracting_setting.account
			self.description = subcontracting_setting.description
		else:
			frappe.throw("Set Account and Description in Subcontracting Settings for Additional Cost")
    
	@frappe.whitelist()
	def get_out_challan_entries(self):
		if self.company:
			subcontracting_setting = frappe.get_doc("Subcontracting Settings", self.company)
			if subcontracting_setting.account:
				self.account = subcontracting_setting.account
				self.description = subcontracting_setting.description
			else:
				frappe.throw("Set Account and Description in Subcontracting Settings for Additional Cost")
		self.subcontracting_out_item_details.clear()
		def fetch_challan_data(table_name, item_details_table):
			return frappe.db.sql(f"""
								SELECT 
									so.name,
									{item_details_table}.item_code,
									{item_details_table}.item_name,
									{item_details_table}.subcontracting_operation,
									{item_details_table}.subcontracting_product_mix,
									{item_details_table}.quantity,
									{item_details_table}.returned_quantity,
									{item_details_table}.uom,
									{item_details_table}.out_type
								FROM 
									`{table_name}` AS {item_details_table}
								LEFT JOIN 
									`tabSubcontracting Out` AS so
									ON so.name = {item_details_table}.parent
								WHERE 
									so.supplier_id = %s 
									AND {item_details_table}.quantity > {item_details_table}.returned_quantity 
									AND so.docstatus = 1
        						ORDER BY 
                					so.name ASC""", self.supplier_id, as_dict=True)


		po_out_challan_data = fetch_challan_data('tabSubcontracting Out Purchase Order Item Details', 'sopi')
		oo_out_challan_data = fetch_challan_data('tabSubcontracting Out Open Order Item Details', 'sooi')
		
		def append_challan_data(challan_data, order_type):
			for entry in challan_data:
				self.append('subcontracting_out_item_details', {
					'subcontracting_out_challan': entry['name'],
					order_type: entry['out_type'],
					'item_code': entry['item_code'],
					'item_name': entry['item_name'],
					'subcontracting_operation': entry['subcontracting_operation'],
					'subcontracting_out_quantity': entry['quantity'],
					'returned_quantity': entry['returned_quantity'],
					# 'available_quantity': get_available_quantity(entry['item_code'], self.source_warehouse),
					'available_quantity':stock_balance(entry['item_code'], self.source_warehouse, self.posting_date, self.posting_time),
					'uom': entry['uom'],
					'is_subcontracting_product_mix': 1 if entry['subcontracting_product_mix'] else 0,
					'subcontracting_product_mix': entry['subcontracting_product_mix'],
				})

		append_challan_data(po_out_challan_data, 'purchase_order')
		append_challan_data(oo_out_challan_data, 'open_order')
  
	@frappe.whitelist()
	def get_item_from_out_item_check_mark(self):
		self.subcontracting_in_rejection_reason.clear()
		self.subcontracting_in_raw_item_details.clear()
		self.subcontracting_in_finished_item_details.clear()
		checked_item = []
		possible = []
		
		for entry in self.get('subcontracting_out_item_details'):
			if entry.item_code and entry.item_code not in checked_item:
				checked_item.append(entry.item_code)

		product_mix_list = frappe.get_all('Subcontracting Product Mix', filters={'disable': 0}, fields=['name'])

		for product_mix in product_mix_list:
			product_mix_items = frappe.get_all('Subcontracting Product Mix Raw Material Details', filters={'parent': product_mix.name}, fields=['item_code'])
			product_mix_raw_items = [item.item_code for item in product_mix_items]

			if all(raw_item in checked_item for raw_item in product_mix_raw_items):
				product_mix_doc = frappe.get_doc('Subcontracting Product Mix',product_mix.name)
				possible.append(product_mix_doc.finished_item_code)
				self.append('subcontracting_in_finished_item_details', {
						'item_code': product_mix_doc.finished_item_code,
						'item_name': product_mix_doc.finished_item_name,
						'is_subcontracting_product_mix': 1,
						'subcontracting_product_mix': product_mix.name,
						'uom': product_mix_doc.default_uom,
						'weight_per_unit':product_mix_doc.weight_per_unit,
						'subcon_weight':product_mix_doc.weight_per_unit,
						'type_of_goods': "Capital Goods" if frappe.db.get_value('Item', product_mix_doc.finished_item_code, 'is_fixed_asset') else 'Input',
					})

		for entry in self.get('subcontracting_out_item_details'):
			if entry.check:
				if entry.item_code not in possible:
					exist = self.get('subcontracting_in_finished_item_details', filters = {'item_code': entry.item_code})
					if not exist:
						weight_per_unit = frappe.get_value('Item', filters={'name': entry.item_code}, fieldname='weight_per_unit') or 0
						self.append('subcontracting_in_finished_item_details', {
							'item_code': entry.item_code,
							'item_name': frappe.get_value('Item', filters={'name': entry.item_code}, fieldname='item_name'),
							'uom':  entry.uom,
							'weight_per_unit':weight_per_unit,
							'subcon_weight':weight_per_unit,
							'type_of_goods': "Capital Goods" if frappe.db.get_value('Item', entry.item_code, 'is_fixed_asset') else 'Input',
						})

	@frappe.whitelist()
	def get_required_raw_item_of_finished_ok_qty(self, ok_qty, item, is_subcontracting_product_mix, subcontracting_product_mix = None, qty=0):	
		existing_row = None
		
		if is_subcontracting_product_mix:
			raw_item_list = frappe.get_all('Subcontracting Product Mix Raw Material Details', filters={'parent': subcontracting_product_mix}, fields=['item_code', 'quantity'])
			for raw_item in raw_item_list:
				for row in self.get('subcontracting_in_raw_item_details', filters = {'item_code': raw_item['item_code'], 'is_subcontracting_product_mix': 1}):
					existing_row = row
					subcontracting_product_mix_quantity = frappe.get_value('Subcontracting Product Mix', {'name': subcontracting_product_mix}, 'quantity')
					for raw_item in raw_item_list:
						if existing_row.item_code == raw_item['item_code']:
							existing_row.required_quantity = (raw_item['quantity'] / subcontracting_product_mix_quantity) * ok_qty
		else:
			for row in self.get('subcontracting_in_raw_item_details', filters = {'item_code': item, 'is_subcontracting_product_mix': 0}):
				if row.item_code == item:
					existing_row = row
					existing_row.required_quantity = ok_qty
					break
		
		if not existing_row:
			if is_subcontracting_product_mix:
				subcontracting_product_mix_quantity = frappe.get_value('Subcontracting Product Mix', {'name': subcontracting_product_mix}, 'quantity')
				raw_item_list = frappe.get_all('Subcontracting Product Mix Raw Material Details', filters={'parent': subcontracting_product_mix}, fields=['item_code', 'quantity'])
				for raw_item in raw_item_list:
					self.append('subcontracting_in_raw_item_details', {
						'item_code': raw_item['item_code'],
						'item_name': frappe.get_value('Item', raw_item['item_code'], 'item_name'),
						'required_quantity': (raw_item['quantity'] / subcontracting_product_mix_quantity) * ok_qty,
						'is_subcontracting_product_mix': 1
					})
			else:
				self.append('subcontracting_in_raw_item_details', {
						'item_code': item,
						'item_name': frappe.get_value('Item', item, 'item_name'),
						'required_quantity': ok_qty
					})
		self.get_total_weight_subcon_weight()
  		

	@frappe.whitelist()
	def get_rejection_reason_for_rejected_qty(self, item, qty, field):
		rejection_exist = False
		rejection_type = frappe.get_value('Subcontracting Rejection Type', {'subcontracting_field': field}, 'name')
		for rej in self.subcontracting_in_rejection_reason:
			if rej.item_code == item and rej.rejection_type == rejection_type:
				rej.rejection_quantity = qty
				rejection_exist = True
				break
		if not rejection_exist:
			self.append('subcontracting_in_rejection_reason', {
				'item_code': item,
				'rejection_type': rejection_type,
				'rejection_quantity': qty
			})

	@frappe.whitelist()
	def get_total_weight_subcon_weight(self):
		for finish in self.get("subcontracting_in_finished_item_details"):
			finish.ok_weight = finish.weight_per_unit * finish.ok_qty if finish.ok_qty else 0
			finish.ok_subcon = finish.subcon_weight * finish.ok_qty if finish.ok_qty else 0
   
			finish.cr_weight = finish.weight_per_unit * finish.cr_qty if finish.cr_qty else 0
			finish.cr_subcon = finish.subcon_weight * finish.cr_qty if finish.cr_qty else 0
   
			finish.mr_weight = finish.weight_per_unit * finish.mr_qty if finish.mr_qty else 0
			finish.mr_subcon = finish.subcon_weight * finish.mr_qty if finish.mr_qty else 0
   
			finish.rw_weight = finish.weight_per_unit * finish.rw_qty if finish.rw_qty else 0
			finish.rw_subcon = finish.subcon_weight * finish.rw_qty if finish.rw_qty else 0

			finish.as_it_is_weight = finish.weight_per_unit * finish.as_it_is_qty if finish.as_it_is_qty else 0
			finish.as_it_is_subcon = finish.subcon_weight * finish.as_it_is_qty if finish.as_it_is_qty else 0
   
			finish.other_weight = finish.weight_per_unit * finish.other_qty if finish.other_qty else 0
			finish.other_subcon = finish.subcon_weight * finish.other_qty if finish.other_qty else 0
