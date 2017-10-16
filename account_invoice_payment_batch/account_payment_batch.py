# -*- coding: utf-8 -*-
##############################################################################
#
# OdooBro - odoobro.contact@gmail.com
#
##############################################################################

import operator
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

MAP_INVOICE_TYPE_PAYMENT_SIGN = {
    'out_invoice': 1,
    'in_refund': 1,
    'in_invoice': -1,
    'out_refund': -1,
}

MAP_INVOICE_TYPE_PARTNER_TYPE = {
    'out_invoice': 'customer',
    'out_refund': 'customer',
    'in_invoice': 'supplier',
    'in_refund': 'supplier',
}

PAYMENT_TYPE_MAP = {
    'out_invoice': 'inbound',
    'in_refund': 'inbound',
    'in_invoice': 'outbound',
    'out_refund': 'outbound',
}


class AccountPaymentBatch(models.TransientModel):
    _name = 'account.payment.batch'
    _inherit = 'account.register.payments'

    line_cr_ids = fields.One2many(
        string='Credit',
        comodel_name='account.payment.batch.line',
        domain=[('type', '=', 'cr')],
        inverse_name='wizard_id'
    )
    line_dr_ids = fields.One2many(
        string='Debit',
        comodel_name='account.payment.batch.line',
        domain=[('type', '=', 'dr')],
        inverse_name='wizard_id'
    )
    line_ids = fields.One2many(
        string='Debit',
        comodel_name='account.payment.batch.line',
        inverse_name='wizard_id'
    )
    balance = fields.Monetary(
        string='Payment difference',
        compute="_compute_balance",
        currency_field='currency_id')
    inv_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Refund'),
        ('in_refund', 'Vendor Refund')])

    @api.constrains('amount')
    def _check_amount(self):
        if not self.amount >= 0.0:
            raise ValidationError(
                _('The payment amount must be strictly positive.'))

    @api.onchange('amount', 'line_dr_ids', 'line_cr_ids')
    def _onchange_amount(self):
        self._compute_balance()

    @api.multi
    def _compute_balance(self):
        for record in self:
            total_cr = total_dr = 0.0
            for l in record.line_cr_ids:
                total_cr += l.amount
            for l in record.line_dr_ids:
                total_dr += l.amount
            self.balance = self.amount + total_cr - total_dr

    @api.model
    def default_get(self, fields):
        ctx = self._context
        inv_type = ctx.get('default_inv_type')
        partner_type = MAP_INVOICE_TYPE_PARTNER_TYPE.get(inv_type)

        res = {
           'inv_type': inv_type,
           'partner_type': partner_type,
           'currency_id': self.env.user.company_id.currency_id.id,
           'payment_type': PAYMENT_TYPE_MAP.get(inv_type)
        }
        return res

    @api.model
    def get_account_id(self, partner, inv_type, journal):
        account_id = None
        if not partner and not journal:
            return account_id
        if inv_type in ('out_invoice', 'out_refund'):
            account_id = partner.property_account_receivable_id.id
        elif inv_type in ('in_invoice', 'in_refund'):
            account_id = partner.property_account_payable_id.id
        else:
            account_id = journal.default_credit_account_id.id or \
                journal.default_debit_account_id.id
        return account_id

    @api.model
    def get_move_lines(self, partner_id, account_id):
        args = [('partner_id', '=', partner_id),
                ('account_id', '=', account_id),
                ('reconciled', '=', False)]
        MoveLine = self.env['account.move.line']
        lines = MoveLine.search(args)
        lines = lines.filtered(lambda r: r.move_id.state == 'posted')
        return lines

    @api.model
    def get_cdr_line(self, currency, lines, partner_type):
        line_dr, line_cr = [(5,)], [(5,)]
        total_credit = total_debit = 0.0
        line_dict = {}
        for line in lines:
            balance = amount_due = 0.0
            if currency:
                if (line.currency_id and
                        currency.id == line.currency_id.id) or \
                        (not line.currency_id and
                         (not line.company_currency_id or
                          line.company_currency_id.id == line.currency_id.id)):
                    balance = abs(line.balance)
                    amount_due = abs(line.amount_residual)
                else:
                    from_currency = None
                    if line.currency_id:
                        from_currency = line.currency_id
                    else:
                        from_currency = line.company_currency_id
                    balance = abs(line.balance)
                    amount_due = abs(line.amount_residual)
                    balance = from_currency.compute(balance, currency)
                    amount_due = from_currency.compute(amount_due, currency)
            if line.credit:
                if partner_type == 'customer':
                    total_credit += amount_due
                else:
                    total_debit += amount_due
            if line.debit:
                if partner_type == 'customer':
                    total_debit += amount_due
                else:
                    total_credit += amount_due
            line_dict.update({line.id: [balance, amount_due]})

        payment_amount = total_debit - total_credit
        if payment_amount < 0.0:
            payment_amount = 0.0

        for line in lines:
            if line.id not in line_dict:
                continue
            balance, amount_due = line_dict[line.id]
            rs = {
                'move_line_id': line.id,
                'type': line.credit and 'cr' or 'dr',
                'account_id': line.account_id.id,
                'balance': balance,
                'amount_due': amount_due,
                'date': line.date,
                'date_due': line.date_maturity,
                'amount': 0.0,
                'currency_id': currency.id,
            }
            if partner_type == 'supplier':
                rs['type'] = rs['type'] == 'cr' and 'dr' or 'cr'
            if rs['type'] == 'dr':
                rs.update({'amount': amount_due})
            elif rs['amount_due']:
                am = min(rs['amount_due'], total_debit)
                rs.update({'amount': am})
                total_debit -= rs['amount_due']
                if total_debit < 0.0:
                    total_debit = 0.0

            if rs['amount_due'] == rs['amount']:
                rs.update({'is_full_payment': True})
            if rs['type'] == 'dr':
                line_dr.append((0, 0, rs))
            else:
                line_cr.append((0, 0, rs))
        return line_cr, line_dr, payment_amount

    @api.onchange('partner_id', 'currency_id', 'inv_type', 'journal_id')
    def onchange_partner_id(self):
        # Checks on received invoice records
        if not self.partner_id or not self.journal_id:
            return False
        account_id = self.get_account_id(self.partner_id, self.inv_type,
                                         self.journal_id)
        lines = self.get_move_lines(self.partner_id.id, account_id)
        line_cr, line_dr, payment_amount = self.get_cdr_line(self.currency_id,
                                                             lines,
                                                             self.partner_type)
        self.line_cr_ids = line_cr
        self.line_dr_ids = line_dr
        self.amount = payment_amount

    @api.multi
    def get_payment_vals(self):
        self.ensure_one()
        res = {
            'journal_id': self.journal_id.id,
            'payment_method_id': self.payment_method_id.id,
            'payment_date': self.payment_date,
            'communication': self.communication,
            'payment_type': self.payment_type,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'partner_type': self.partner_type,
        }
        return res

    @api.model
    def split_dcr_line(self, lines, rev=False):
        line_dcr = []
        for l in lines:
            line_dcr.append({'line_id': l.move_line_id,
                             'amount': l.amount})
        line_dcr = sorted(line_dcr, key=operator.itemgetter('amount'),
                          reverse=rev)
        return line_dcr

    @api.model
    def create_partial_reconcile(self, debit, credit, amount, partner_type,
                                 amount_curr=0.0, currency_id=None):
        debit_move_id = partner_type == 'customer' and debit.id or credit.id
        credit_move_id = partner_type == 'customer' and credit.id or debit.id
        return self.env['account.partial.reconcile'].create({
            'debit_move_id': debit_move_id,
            'credit_move_id': credit_move_id,
            'amount': amount,
            'amount_currency': amount_curr,
            'currency_id': currency_id,
        })

    @api.multi
    def create_payment(self):
        self.ensure_one()

        if self.balance < 0.0:
            raise UserError(_("`the Payment difference` must be larger than "
                            "or equal to  0.0"))
        move_lines = self.env['account.move.line']
        line_drs = self.split_dcr_line(self.line_dr_ids, True)
        line_crs = self.split_dcr_line(self.line_cr_ids)

        account_id = None

        # priority for the equal amount between debit and credit
        for l_dr in line_drs:
            if l_dr['amount'] <= 0.0:
                continue
            if not account_id:
                account_id = l_dr['line_id'].account_id.id
            for l_cr in line_crs:
                if l_dr['amount'] == l_cr['amount']:
                    self.create_partial_reconcile(l_dr['line_id'],
                                                  l_cr['line_id'],
                                                  l_dr['amount'],
                                                  self.partner_type)
                    l_dr['amount'] = l_cr['amount'] = 0.0
                    move_lines += l_dr['line_id'] + l_cr['line_id']
                break

        for l_dr in line_drs:
            if l_dr['amount'] <= 0.0:
                continue
            for l_cr in line_crs:
                if l_cr['amount'] <= 0.0:
                    continue
                amount_rec = min(l_dr['amount'], l_cr['amount'])
                self.create_partial_reconcile(l_dr['line_id'],
                                              l_cr['line_id'],
                                              amount_rec,
                                              self.partner_type)
                l_dr['amount'] -= amount_rec
                l_cr['amount'] -= amount_rec
                if l_dr['line_id'] not in move_lines:
                    move_lines += l_dr['line_id']
                if l_cr['line_id'] not in move_lines:
                    move_lines += l_cr['line_id']
                if l_dr['amount'] <= 0.0:
                    break
        if self.amount:
            # Create payment
            payment = self.env['account.payment'
                               ].create(self.get_payment_vals())
            payment.post()
            if line_drs:
                pm_args = [('payment_id', '=', payment.id),
                           ('reconciled', '=', False),
                           ('account_id', '=', account_id)]
                pm_move_lines = self.env['account.move.line'].search(pm_args)
                for l_dr in line_drs:
                    if l_dr['amount'] <= 0.0:
                        continue
                    for pm_line in pm_move_lines:
                        cr_amount = abs(pm_line.amount_residual)
                        if cr_amount <= 0.0:
                            continue
                        amount_rec = min(l_dr['amount'], cr_amount)
                        self.create_partial_reconcile(l_dr['line_id'],
                                                      pm_line,
                                                      amount_rec,
                                                      self.partner_type)
                        l_dr['amount'] -= amount_rec
                        if l_dr['line_id'] not in move_lines:
                            move_lines += l_dr['line_id']
                        if l_dr['amount'] <= 0.0:
                            break
        if move_lines:
            move_lines.compute_full_after_batch_reconcile()

        return {'type': 'ir.actions.act_window_close'}
