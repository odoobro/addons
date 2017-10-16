# -*- coding: utf-8 -*-
##############################################################################
#
# OdooBro - odoobro.contact@gmail.com
#
##############################################################################

{
    'name': 'Account Invoice Payment Batch',
    'version': '1.0.1',
    'category': 'OdooBro Apps',
    'summary': """
Build a tool to pay many Customer Invoices / Vendor Bills at the same time and
take into account the advance payments.
    """,
    'author': 'OdooBro - odoobro.contact@gmail.com',
    'website': 'http://odoobro.com',
    'depends': [
        'account'
    ],
    'data': [
        'account_payment_batch_view.xml',
    ],

    'test': [],
    'demo': [],
    'images': ['images/main_cover.png'],
    'installable': True,
    'active': False,
    'application': True,
    'price': 39.99,
    'currency': 'EUR'
}
