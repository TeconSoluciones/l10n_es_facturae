# -*- encoding: utf-8 -*-
##############################################################################
#
#    Tecon Soluciones Informáticas, S.L.
#    http://www.tecon.es
#    All Rights Reserved
#    
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see http://www.gnu.org/licenses/.
#
##############################################################################
from osv import osv,fields

class res_partner(osv.osv):
  _name = 'res.partner.address'
  _inherit = 'res.partner.address'
  
  _columns = {
              'fiscal_code':fields.char('Cod. oficina contable',size=10),
              #'fiscal_address':fields.many2one('res.partner.address',ondelete='set null',string='Dirección oficina contable'),
              'receiver_code':fields.char('Cod. órgano gestor',size=10),
              #'receiver_address':fields.many2one('res.partner.address',ondelete='set null', string='Dirección órgano contable'),
              'payer_code':fields.char('Cod. unidad tramitadora',size=10),
              #'payer_address':fields.many2one('res.partner.address',ondelete='set null',  string='Dirección unidad tramitadora'),
              }

res_partner()