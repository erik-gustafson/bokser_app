"""Odoo-shell fixture for bokser_sos_mirror_local ONLY; contains no credentials.
Run after the synthetic-master-20261010 account/service-user fixture is created.
Never deploy this script as a production initializer.
"""
assert env.cr.dbname=='bokser_sos_mirror_local'
account=env['bokser.sos.account'].search([('code','=','synthetic-master-20261010')],limit=1)
user=env['res.users'].search([('login','=','synthetic_master_api_20261010')],limit=1)
assert account and user
company=account.company_id
def native_account(code,kind):
    result=env['account.account'].search([('code','=',code),('company_ids','in',company.ids)],limit=1)
    if not result:result=env['account.account'].create({'name':'Synthetic API '+kind,'code':code,'account_type':kind,'company_ids':[(6,0,company.ids)]})
    return result
income=native_account('919911','income');cash=native_account('919912','asset_cash')
receivable=native_account('919913','asset_receivable');receivable.reconcile=True
payable=native_account('919914','liability_payable');payable.reconcile=True
def journal(code,kind,default):
    result=env['account.journal'].search([('code','=',code),('company_id','=',company.id)],limit=1)
    if not result:result=env['account.journal'].create({'name':'Synthetic API '+kind,'code':code,'company_id':company.id,'type':kind,'default_account_id':default.id})
    return result
sale=journal('MTS','sale',income);bank=journal('MTB','bank',cash)
product=env['product.product'].search([('default_code','=','SYNTHETIC_MIRROR_API_ITEM')],limit=1)
if not product:product=env['product.product'].create({'name':'Synthetic API item','default_code':'SYNTHETIC_MIRROR_API_ITEM','type':'consu','is_storable':True,'property_account_income_id':income.id,'taxes_id':[(5,0,0)],'supplier_taxes_id':[(5,0,0)]})
fee=env['product.product'].search([('default_code','=','SYNTHETIC_MIRROR_API_FEE')],limit=1)
if not fee:fee=env['product.product'].create({'name':'Synthetic API fee','default_code':'SYNTHETIC_MIRROR_API_FEE','type':'service','property_account_income_id':income.id})
warehouse=env['stock.warehouse'].search([('company_id','=',company.id)],limit=1)
refs=env['bokser.sos.reference']
for kind,key,target in [('item','100',product),('uom','1',product.uom_id),('currency','default',company.currency_id),
        ('warehouse','1',warehouse),('warehouse','default',warehouse),('sales_journal','default',sale),
        ('payment_journal','33',bank),('payment_method_line','88',bank.inbound_payment_method_line_ids[:1]),
        ('receipt_type','1',warehouse.in_type_id),('shipment_type','1',warehouse.out_type_id),
        ('return_type','1',warehouse.in_type_id),('rma_type','1',warehouse.in_type_id),
        ('income_account','default',income),('fee_product','shippingAmount',fee),('fee_product','discountAmount',fee)]:
    if not refs.search_count([('account_id','=',account.id),('kind','=',kind),('source_key','=',key)]):
        refs.create({'account_id':account.id,'kind':kind,'source_key':key,kind+'_id':target.id})
for entity,identifier in [('customer','17'),('vendor','18')]:
    p={'schema_version':1,'entity':entity,'source_id':identifier,'observed_at':'2026-10-10T12:00:00Z',
        'values':{'name':'Synthetic HTTPS '+entity,'phone':'','email':'','website':''}}
    result=env['bokser.sos.account'].with_user(user).import_partner(account.code,company.id,p)
    env['res.partner'].browse(result['partner_id']).write({'property_account_receivable_id':receivable.id,'property_account_payable_id':payable.id})
env['ir.config_parameter'].set_param('bokser_sos_mirror.transaction_cutoff','')
env.cr.commit()
env.registry.signal_changes()
print('Disposable transaction mappings ready')
