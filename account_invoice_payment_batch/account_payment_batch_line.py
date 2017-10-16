# -*- coding: utf-8 -*-
##############################################################################
#
# OdooBro - odoobro.contact@gmail.com
#
##############################################################################


from odoo import api, fields, models, _


class AccountPaymentBatchLine(models.TransientModel):

    _name = "account.payment.batch.line"

    wizard_id = fields.Many2one(
        comodel_name='account.payment.batch',
        string='Wizard'
    )
    move_line_id = fields.Many2one(
        string='Journal Item',
        comodel_name='account.move.line',
        required=False
    )
    account_id = fields.Many2one(
        string="Account",
        comodel_name="account.account",
        related="move_line_id.account_id",
        readonly=True)
    date = fields.Date(
        string="Date",
        related="move_line_id.date",
        readonly=True)
    date_maturity = fields.Date(
        string="Due Date",
        related="move_line_id.date_maturity",
        readonly=True)
    balance = fields.Monetary(
        string='Original Amount',
        readonly=True,
        currency_field='currency_id'
    )
    amount_due = fields.Monetary(
        string='Open Balance',
        readonly=True,
        currency_field='currency_id'
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='wizard_id.currency_id',
        readonly=True,
        help='Utility field to express amount currency'
    )
    is_full_payment = fields.Boolean(
        string="Full Payment")
    type = fields.Selection([('dr', 'Debit'), ('cr', 'Credit')],
                            string='Dr/Cr')

    @api.onchange('is_full_payment')
    def onchange_full_payment(self):
        for r in self:
            if r.is_full_payment:
                r.amount = r.amount_due

    @api.onchange('amount')
    def onchange_amount(self):
        res = {}
        for r in self:
            if r.amount == r.amount_due:
                r.is_full_payment = True
            elif r.amount > r.amount_due:
                r.amount = r.amount_due
                r.is_full_payment = True
                if not res:
                    res = {'warning':
                           {'title': 'Warning!',
                            'message':
                            _('Amount cannot be larger than Opening balance')}}
            else:
                r.is_full_payment = False
        if res:
            return res
