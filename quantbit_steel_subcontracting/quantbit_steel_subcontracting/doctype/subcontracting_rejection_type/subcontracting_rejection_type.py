# Copyright (c) 2025, Quantbit Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SubcontractingRejectionType(Document):
	def before_save(self):
		self.subcontracting_field = f"{self.rejection_type_name.lower().replace(' ', '_')}_qty"