# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2009 Alejandro Sanchez (http://www.asr-oss.com) All Rights Reserved.
#                       Alejandro Sanchez <alejandro@asr-oss.com>
#    $Id$
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import pooler
import wizard
import base64
import netsvc
from tools.translate import _
import subprocess
import os
import sys

reload(sys)
sys.setdefaultencoding("utf8")

logger = netsvc.Logger()

facturae_form = """<?xml version="1.0"?>
<form string="Create Factura-E">
    <label string="Do you want to Create Factura-E?"/>
</form>"""

facturae_fields = {}

export_form = """<?xml version="1.0"?>
<form string="Payment order export">
    <field name="facturae" filename="facturae_fname"/>
    <field name="facturae_fname" invisible="1"/>
    <field name="note" colspan="4" nolabel="1"/>
</form>"""

export_fields = {
    'facturae' : {
        'string':'Factura-E file',
        'type':'binary',
        'required': False,
        'readonly':True,
    },
    'facturae_fname': {'string':'File name', 'type':'char', 'size':64},
    'note' : {'string':'Log', 'type':'text'},
}

def conv_ascii(text):
    """Convierte vocales accentuadas, ñ y ç a sus caracteres equivalentes ASCII"""
    old_chars = ['á','é','í','ó','ú','à','è','ì','ò','ù','ä','ë','ï','ö','ü','â','ê','î','ô','û','Á','É','Í','Ú','Ó','À','È','Ì','Ò','Ù','Ä','Ë','Ï','Ö','Ü','Â','Ê','Î','Ô','Û','ñ','Ñ','ç','Ç','ª','º']
    new_chars = ['a','e','i','o','u','a','e','i','o','u','a','e','i','o','u','a','e','i','o','u','A','E','I','O','U','A','E','I','O','U','A','E','I','O','U','A','E','I','O','U','n','N','c','C','a','o']
    for old, new in zip(old_chars, new_chars):
        text = text.replace(unicode(old,'UTF-8'), new)
    return text

class Log(Exception):
    def __init__(self):
        self.content = ""
        self.error = False
    def add(self, s, error=True):
        self.content = self.content + s
        if error:
            self.error = error
    def __call__(self):
        return self.content
    def __str__(self):
        return self.content


def _create_facturae_file(self, cr, uid, data, context):

    def _format_xml():
        #formato y definicion del fichero xml
        texto = '﻿<?xml version="1.0" encoding="UTF-8"?>'
        #texto = '<fe:Facturae xmlns:fe="http://www.facturae.es/Facturae/2007/v3.1/Facturae" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        texto = '<fe:Facturae xmlns:fe="http://www.facturae.es/Facturae/2009/v3.2/Facturae" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.facturae.es/Facturae/2009/v3.2/Facturae">'
        return texto

    def _persona(vat):
        texto = ''
        if vat[2:3].isdigit() == True:
            texto = 'F'
        else:
            texto = 'J'
        return texto

    def _apoyo_batch():

        texto = ''
        currency = invoice.currency_id

        texto += '<TotalInvoicesAmount>'
        texto += '<TotalAmount>' + str('%.2f' % invoice.amount_total) + '</TotalAmount>'
        texto += '</TotalInvoicesAmount>'

        texto += '<TotalOutstandingAmount>'
        texto += '<TotalAmount>' + str('%.2f' % invoice.amount_total) + '</TotalAmount>'
        texto += '</TotalOutstandingAmount>'

        texto += '<TotalExecutableAmount>'
        texto += '<TotalAmount>' + str('%.2f' % invoice.amount_total) + '</TotalAmount>'
        texto += '</TotalExecutableAmount>'
        #I.AFG.
        texto += '<InvoiceCurrencyCode>' + currency.code + '</InvoiceCurrencyCode>'
        #texto += '<InvoiceCurrencyCode>' + currency.name + '</InvoiceCurrencyCode>'
        #F.AFG

        return texto

    def _header_facturae(cr, context):

        company_partner_obj = invoice.company_id.partner_id        

        #schemaversion = '3.1'
        schemaversion = '3.2'
        modality = 'I'
        
        if not invoice.number:
            log.add(_('User error:\n\nCan not create Factura-E file if invoice has no number.'))
            raise log

        if company_partner_obj.vat:
            BatchIdentifier = invoice.number + company_partner_obj.vat
        else:
            log.add(_('User error:\n\nCompany %s has no VAT number.') % (company_partner_obj.name), True)
            raise log

        texto = ''
        texto += '<FileHeader>'
        texto += '<SchemaVersion>' + schemaversion + '</SchemaVersion>'
        texto += '<Modality>' + modality + '</Modality>'
        texto += '<InvoiceIssuerType>EM</InvoiceIssuerType>'
        texto += '<Batch>'
        texto += '<BatchIdentifier>' + BatchIdentifier + '</BatchIdentifier>'
        texto += '<InvoicesCount>1</InvoicesCount>'
        texto += _apoyo_batch()
        texto += '</Batch>'
        texto += '</FileHeader>'
        return texto

    def _parties_facturae(cr, context):

        pool = pooler.get_pool(cr.dbname)
        company_obj = invoice.company_id
        company_partner_obj = company_obj.partner_id
        invoice_partner_obj = invoice.partner_id
        invoice_partner_address_obj = invoice.address_invoice_id

        #obtencion direccion company recogemos la de facura adress_get si no encuentra invoice devuelve primera
        company_address_id = pool.get('res.partner').address_get(cr, uid, [company_obj.partner_id.id], ['invoice'])
        if not company_address_id['invoice']:
            log.add(_('User error:\n\nCompany %s does not have an invoicing address.') % (company_partner_obj.name))
            raise log
        company_address_obj = pool.get('res.partner.address').browse(cr, uid, company_address_id['invoice'])

        #obtencion de la direccion del partner
        partner_address_invoice = invoice.address_invoice_id
        
        tipo_seller = _persona(company_partner_obj.vat)

        if invoice_partner_obj.vat:
            tipo_buyer = _persona(invoice_partner_obj.vat)
        else:
            log.add(_('User error:\n\nPartner %s does not have a VAT number.') % (invoice_partner_obj.name), True)
            raise log
        
        texto = ''
        texto += '<Parties>'
        texto += '<SellerParty>'
        texto += '<TaxIdentification>'
        texto += '<PersonTypeCode>' + tipo_seller + '</PersonTypeCode>'
        texto += '<ResidenceTypeCode>U</ResidenceTypeCode>'
        texto += '<TaxIdentificationNumber>' + company_partner_obj.vat + '</TaxIdentificationNumber>'
        texto += '</TaxIdentification>'
        
        if tipo_seller == 'F':
            texto += '<Individual>'
            texto += '<Name>' + company_partner_obj.name + '</Name>'
            texto += '<FirstSurname></FirstSurname>'
            texto += '<SecondSurname></SecondSurname>'
        else:
            texto += '<LegalEntity>'
            texto += '<CorporateName>' + company_obj.name + '</CorporateName>'
            texto += '<TradeName>' + company_obj.name + '</TradeName>'

        #Fijo hasta que se tome una decision no son obligatorios
        #texto += '<RegistrationData>'
        #texto += '<Book>1</Book>'
        #texto += '<RegisterOfCompaniesLocation>12AP22</RegisterOfCompaniesLocation>'
        #texto += '<Sheet>3</Sheet>'
        #texto += '<Folio>15</Folio>'
        #texto += '<Section>2</Section>'
        #texto += '<Volume>12</Volume>'
        #texto += '<AdditionalRegistrationData>Sin datos</AdditionalRegistrationData>'
        #texto += '</RegistrationData>'
        #fin
        texto += '<AddressInSpain>'
        if company_address_obj.street:
            if company_address_obj.street2:
                texto += '<Address>' + company_address_obj.street + ' ' + company_address_obj.street2 + '</Address>'
            else:
                texto += '<Address>' + company_address_obj.street + '</Address>'
        else:
            log.add(_('User error:\n\nCompany %s has no street.') % (company_partner_obj.name), True)
            raise log
        if company_address_obj.zip:
            texto += '<PostCode>' + company_address_obj.zip + '</PostCode>'
        else:
            log.add(_('User error:\n\nCompany %s has no zip code.') % (company_partner_obj.name), True)
            raise log
        if company_address_obj.city:
            texto += '<Town>' + company_address_obj.city + '</Town>'
        else:
            log.add(_('User error:\n\nCompany %s has no city.') % (company_partner_obj.name), True)
            raise log
        if  company_address_obj.state_id.name:
            texto += '<Province>' + company_address_obj.state_id.name + '</Province>'
        else:
            log.add(_('User error:\n\nCompany %s has no province.') % (company_partner_obj.name), True)
            raise log
        if company_address_obj.country_id.code_3166:
            texto += '<CountryCode>' + company_address_obj.country_id.code_3166 + '</CountryCode>'
        else:
            log.add(_('User error:\n\nCompany %s has no country.') % (company_partner_obj.name), True)
            raise log
        texto += '</AddressInSpain>'

        texto += '<ContactDetails>'
        if company_address_obj.phone:
            texto += '<Telephone>' + company_address_obj.phone + '</Telephone>'
        if company_address_obj.fax:
            texto += '<TeleFax>' + company_address_obj.fax + '</TeleFax>'
        if company_partner_obj.website:
            texto += '<WebAddress>' + company_partner_obj.website + '</WebAddress>'
        if company_address_obj.email:
            texto += '<ElectronicMail>' + company_address_obj.email + '</ElectronicMail>'
        if company_address_obj.name:
            texto += '<ContactPersons>' + company_address_obj.name + '</ContactPersons>'
        texto += '</ContactDetails>'

        if tipo_seller == 'F':
            texto += '</Individual>'
        else:
            texto += '</LegalEntity>'

        texto += '</SellerParty>'
        texto += '<BuyerParty>'
        texto += '<TaxIdentification>'
        texto += '<PersonTypeCode>' + tipo_buyer + '</PersonTypeCode>'
        texto += '<ResidenceTypeCode>U</ResidenceTypeCode>'
        texto += '<TaxIdentificationNumber>' + invoice_partner_obj.vat + '</TaxIdentificationNumber>'
        texto += '</TaxIdentification>'
        
        # Añadimos los códigos del centro receptor de la factura.
        texto += '<AdministrativeCentres>'
        
        # Datos comunes
        ent_street = invoice.address_contact_id and invoice.address_contact_id.street or ''
        ent_postcode = invoice.address_contact_id and invoice.address_contact_id.zip or ''
        ent_town = invoice.address_contact_id and invoice.address_contact_id.city or ''
        ent_province = invoice.address_contact_id and invoice.address_contact_id.state_id.name or ''
        ent_country = invoice.address_contact_id and invoice.address_contact_id.country_id.code_3166 or ''
        
        # Oficina contable
        fiscal_code = invoice.address_contact_id and invoice.address_contact_id.fiscal_code or ''
        texto += '<AdministrativeCentre>'
        texto += '<CentreCode>' + fiscal_code + '</CentreCode>'
        texto += '<RoleTypeCode>01</RoleTypeCode>'
        texto += '<AddressInSpain>'
        texto += '<Address>' + ent_street + '</Address>'
        texto += '<PostCode>' + ent_postcode + '</PostCode>'
        texto += '<Town>' + ent_town + '</Town>'
        texto += '<Province>' + ent_province + '</Province>'
        texto += '<CountryCode>' + ent_country + '</CountryCode>'
        texto += '</AddressInSpain>'
        texto += '</AdministrativeCentre>'
        
        # Órgano gestor
        receiver_code = invoice.address_contact_id and invoice.address_contact_id.receiver_code or ''
        texto += '<AdministrativeCentre>'
        texto += '<CentreCode>' + receiver_code + '</CentreCode>'
        texto += '<RoleTypeCode>02</RoleTypeCode>'
        texto += '<AddressInSpain>'
        texto += '<Address>' + ent_street + '</Address>'
        texto += '<PostCode>' + ent_postcode + '</PostCode>'
        texto += '<Town>' + ent_town + '</Town>'
        texto += '<Province>' + ent_province + '</Province>'
        texto += '<CountryCode>' + ent_country + '</CountryCode>'
        texto += '</AddressInSpain>'
        texto += '</AdministrativeCentre>'
        
        # Unidad tramitadora
        payer_code = invoice.address_contact_id and invoice.address_contact_id.payer_code or ''
        texto += '<AdministrativeCentre>'
        texto += '<CentreCode>' + payer_code + '</CentreCode>'
        texto += '<RoleTypeCode>03</RoleTypeCode>'
        texto += '<AddressInSpain>'
        texto += '<Address>' + ent_street + '</Address>'
        texto += '<PostCode>' + ent_postcode + '</PostCode>'
        texto += '<Town>' + ent_town + '</Town>'
        texto += '<Province>' + ent_province + '</Province>'
        texto += '<CountryCode>' + ent_country + '</CountryCode>'
        texto += '</AddressInSpain>'
        texto += '</AdministrativeCentre>'        
        
        texto += '</AdministrativeCentres>'

        if tipo_buyer == 'F':
            texto += '<Individual>'
            texto += '<Name>' + invoice_partner_obj.name + '</Name>'
            texto += '<FirstSurname></FirstSurname>'
            texto += '<SecondSurname></SecondSurname>'
        else:
            texto += '<LegalEntity>'
            texto += '<CorporateName>' + invoice_partner_obj.name + '</CorporateName>'


        texto += '<AddressInSpain>'
        if invoice_partner_address_obj.street:
            if company_address_obj.street2:
                texto += '<Address>' + invoice_partner_address_obj.street + ' ' + company_address_obj.street2 + '</Address>'
            else:
                texto += '<Address>' + invoice_partner_address_obj.street + '</Address>'
        else:
            log.add(_('User error:\n\nPartner %s has no street.') % (invoice_partner_address_obj.name), True)
            raise log
        if invoice_partner_address_obj.zip:
            texto += '<PostCode>' + invoice_partner_address_obj.zip + '</PostCode>'
        else:
            log.add(_('User error:\n\nPartner %s has no zip code.') % (invoice_partner_obj.name), True)
            raise log

        if invoice_partner_address_obj.city:
            texto += '<Town>' + invoice_partner_address_obj.city + '</Town>'
        else:
            log.add(_('User error:\n\nPartner %s has no city.') % (invoice_partner_obj.name), True)
            raise log
        if invoice_partner_address_obj.state_id.name:
            texto += '<Province>' + invoice_partner_address_obj.state_id.name + '</Province>'
        else:
            log.add(_('User error:\n\nPartner %s has no province.') % (invoice_partner_obj.name), True)
            raise log
        if invoice_partner_address_obj.country_id.code_3166:
            texto += '<CountryCode>' + invoice_partner_address_obj.country_id.code_3166 + '</CountryCode>'
        else:
            log.add(_('User error:\n\nPartner %s has no country.') % (invoice_partner_obj.name), True)
            raise log
        texto += '</AddressInSpain>'

        texto += '<ContactDetails>'
        if invoice_partner_address_obj.phone:
            texto += '<Telephone>' + invoice_partner_address_obj.phone + '</Telephone>'
        if invoice_partner_address_obj.fax:
            texto += '<TeleFax>' + invoice_partner_address_obj.fax + '</TeleFax>'
        if invoice_partner_obj.website:
            texto += '<WebAddress>' + invoice_partner_obj.website + '</WebAddress>'
        if invoice_partner_address_obj.email:
            texto += '<ElectronicMail>' + invoice_partner_address_obj.email + '</ElectronicMail>'
        if invoice_partner_address_obj.name:
            texto += '<ContactPersons>' + invoice_partner_address_obj.name + '</ContactPersons>'
        texto += '</ContactDetails>'

        if tipo_buyer == 'F':
            texto += '</Individual>'
        else:
            texto += '</LegalEntity>'
        texto += '</BuyerParty>'
        texto += '</Parties>'
        return texto

    def _taxes_output():
        
        texto = ''
        rate = 0.0
        taxes_withhel = 0.0

        texto += '<TaxesOutputs>'

        for l in invoice.tax_line:
            taxes_withhel += l.base_amount
            texto += '<Tax>'
            texto += '<TaxTypeCode>01</TaxTypeCode>'
            cr.execute('SELECT t.amount FROM account_tax t WHERE t.tax_code_id =%s',(l.tax_code_id.id,))
            res = cr.fetchone()
            texto += '<TaxRate>' + str('%.2f' % (res[0] * 100)) + '</TaxRate>'
            texto += '<TaxableBase>'
            texto += '<TotalAmount>' + str('%.2f' % l.base_amount) + '</TotalAmount>'
            texto += '</TaxableBase>'
            texto += '<TaxAmount>'
            texto += '<TotalAmount>' + str('%.2f' % l.tax_amount) + '</TotalAmount>'
            texto += '</TaxAmount>'
            texto += '</Tax>'

        texto += '</TaxesOutputs>'

        texto += '<TaxesWithheld>'
        texto += '<Tax>'
        texto += '<TaxTypeCode>01</TaxTypeCode>'
        texto += '<TaxRate>0.00</TaxRate>'
        texto += '<TaxableBase>'
        texto += '<TotalAmount>' + str('%.2f' % taxes_withhel) + '</TotalAmount>'
        texto += '</TaxableBase>'
        texto += '<TaxAmount>'
        texto += '<TotalAmount>0.00</TotalAmount>'
        texto += '</TaxAmount>'
        texto += '</Tax>'
        texto += '</TaxesWithheld>'

        return texto

    def _invoice_totals():
        
        total_gross_amount = 0.0
        texto = ''
        
        for line in invoice.invoice_line:
            total_gross_amount += line.price_subtotal

        texto += '<InvoiceTotals>'
        texto += '<TotalGrossAmount>' + str('%.2f' % total_gross_amount) + '</TotalGrossAmount>'

        #si se utilizaran los anteriores aqui se le restaria descuentos y sumarian gastos
        texto += '<TotalGrossAmountBeforeTaxes>' + str('%.2f' % total_gross_amount) + '</TotalGrossAmountBeforeTaxes>'
        # I. AFG
        #texto += '<TotalTaxOutputs>' + str('%.2f' % invoice.amount_tax) + '</TotalTaxOutputs>'
        if invoice.type in ['in_refund','out_refund'] :
          texto += '<TotalTaxOutputs>' + str('%.2f' % -invoice.amount_tax) + '</TotalTaxOutputs>'
        else :
          texto += '<TotalTaxOutputs>' + str('%.2f' % invoice.amount_tax) + '</TotalTaxOutputs>'
        # F. AFG
        texto += '<TotalTaxesWithheld>0.00</TotalTaxesWithheld>'
        texto += '<InvoiceTotal>' + str('%.2f' % invoice.amount_total) + '</InvoiceTotal>'
        #aqui se descontaria los pagos realizados a cuenta
        texto += '<TotalOutstandingAmount>' + str('%.2f' % invoice.amount_total) + '</TotalOutstandingAmount>'
        texto += '<TotalExecutableAmount>' + str('%.2f' % invoice.amount_total) + '</TotalExecutableAmount>'

        texto += '</InvoiceTotals>'
        return texto

    def _invoice_items():
        
        rate = 0.0
        texto = ''
        texto += '<Items>'
        
        for line in invoice.invoice_line:
            texto += '<InvoiceLine>'
            texto += '<ItemDescription>' + line.name + '</ItemDescription>'
            texto += '<Quantity>' + str(line.quantity) + '</Quantity>'
            texto += '<UnitPriceWithoutTax>' + str('%.6f' % line.price_unit) + '</UnitPriceWithoutTax>'
            texto += '<TotalCost>' + str('%.6f' % (line.quantity * line.price_unit)) + '</TotalCost>'
            texto += '<DiscountsAndRebates>'
            texto += '<Discount>'
            texto += '<DiscountReason>Descuento</DiscountReason>'
            texto += '<DiscountRate>' + str('%.4f' % line.discount) + '</DiscountRate>'
            # I.AFG
            #texto += '<DiscountAmount>' + str('%.2f' % ( (line.price_unit*line.quantity) - line.price_subtotal)) + '</DiscountAmount>'
            texto += '<DiscountAmount>' + str('%.6f' % ( (line.price_unit*line.quantity) * (line.discount/100))) + '</DiscountAmount>'
            # F.AFG
            texto += '</Discount>'
            texto += '</DiscountsAndRebates>'
            texto += '<GrossAmount>' + str('%.6f' % line.price_subtotal) + '</GrossAmount>'
            texto += '<TaxesWithheld>'
            texto += '<Tax>'
            texto += '<TaxTypeCode>01</TaxTypeCode>'
            texto += '<TaxRate>0.00</TaxRate>'
            texto += '<TaxableBase>'
            texto += '<TotalAmount>' + str('%.2f' % line.price_subtotal) + '</TotalAmount>'
            texto += '</TaxableBase>'
            texto += '</Tax>'
            texto += '</TaxesWithheld>'
            texto += '<TaxesOutputs>'
            for l in line.invoice_line_tax_id:
                rate = '%.2f' % (l.amount * 100)
                texto += '<Tax>'
                texto += '<TaxTypeCode>01</TaxTypeCode>'
                texto += '<TaxRate>' + str(rate) + '</TaxRate>'
                texto += '<TaxableBase>'
                texto += '<TotalAmount>' + str('%.2f' % line.price_subtotal) + '</TotalAmount>'
                texto += '</TaxableBase>'
                texto += '</Tax>'
            texto += '</TaxesOutputs>'
            texto += '</InvoiceLine>'

        texto += '</Items>'
        return texto
    
    def _invoice_payments():
        
        rate = 0.0
        texto = ''
        texto += '<PaymentDetails>'
        
        # Antes de nada, obtenemos el conjunto de vencimientos. Para ello, buscamos los apuntes contra 
        # la misma cuenta contable definida en la factura (la cuenta de cliente).
        if invoice.account_id :
          inv_account_id = invoice.account_id.id
        else :
          log.add(_('User error:\n\nNo se ha definido una cuenta contable para la factura.'), True)
          raise log

        move_obj = invoice.move_id
        move_lines = invoice.move_id.line_id

        for move in move_lines :
          # Con esto evitamos incluir las líneas que no se corresponden con vencimientos.
          if not move.account_id or (move.account_id.id <> inv_account_id) :
            continue
          texto += '<Installment>'
          date_maturity = invoice.date_invoice
          if move.date_maturity :
            date_maturity = move.date_maturity
          texto += '<InstallmentDueDate>' + date_maturity + '</InstallmentDueDate>'
          if move.debit > move.credit :
            pay_amount = move.debit
          else :
            pay_amount = -1 * move.credit
          texto += '<InstallmentAmount>' + str('%.2f' % pay_amount) + '</InstallmentAmount>'
          # Nos aseguramos de que se ha seleccionado el tipo de pago.
          if (not invoice.payment_type) or (not invoice.payment_type.face_code) :
            log.add(_('User error:\n\nNo se ha seleccionado un tipo de pago correcto en la factura.'), True)
            raise log
          texto += '<PaymentMeans>' + invoice.payment_type.face_code + '</PaymentMeans>'
          
          # En función del tipo de pago seleccionado, debemos añadir la cuenta corriente de
          # la empresa, o la cuenta corriente del cliente.
          # TRANSFERENCIA
          if not invoice.partner_bank_id :
            log.add(_('User error:\n\nNo se ha seleccionado una cuenta bancaria en la factura.'), True)
            raise log
          if invoice.payment_type.face_code == '02' :
            texto += '<AccountToBeDebited>'
            texto += '<IBAN>' + invoice.partner_bank_id.iban + '</IBAN>'
            texto += '</AccountToBeDebited>'
          else :
            texto += '<AccountToBeCredited>'
            texto += '<IBAN>' + invoice.partner_bank_id.iban + '</IBAN>'
            texto += '</AccountToBeCredited>'
          texto += '</Installment>'


        texto += '</PaymentDetails>'
        return texto

    def _invoices_facturae():

        texto = ''
        texto += '<Invoices>'
        texto += '<Invoice>'
        texto += '<InvoiceHeader>'
        texto += '<InvoiceNumber>' + invoice.number + '</InvoiceNumber>'
        texto += '<InvoiceSeriesCode>' + invoice.number + '</InvoiceSeriesCode>'
        texto += '<InvoiceDocumentType>FC</InvoiceDocumentType>'
        texto += '<InvoiceClass>OO</InvoiceClass>'
        texto += '</InvoiceHeader>'
        texto += '<InvoiceIssueData>'
        texto += '<IssueDate>' + invoice.date_invoice + '</IssueDate>'
        # I.AFG
        texto += '<InvoiceCurrencyCode>' + invoice.currency_id.code + '</InvoiceCurrencyCode>'
        texto += '<TaxCurrencyCode>' + invoice.currency_id.code + '</TaxCurrencyCode>'
        #texto += '<InvoiceCurrencyCode>' + invoice.currency_id.name + '</InvoiceCurrencyCode>'        
        #texto += '<TaxCurrencyCode>' + invoice.currency_id.name + '</TaxCurrencyCode>'
        # F.AFG
        texto += '<LanguageName>es</LanguageName>'
        texto += '</InvoiceIssueData>'
        texto += _taxes_output()
        texto += _invoice_totals()
        texto += _invoice_items()
        texto += _invoice_payments()
        
        # Añadimos posibles notas o textos adicionales que se quieran incluir en la factura.
        texto += '<AdditionalData>'
        texto_adicional = ''

        if invoice.comment :
          texto_adicional += str(invoice.comment)
        texto += '<InvoiceAdditionalInformation>' + str(texto_adicional) + '</InvoiceAdditionalInformation>'
        texto += '</AdditionalData>'
        
        texto += '</Invoice>'
        texto += '</Invoices>'
        return texto

    def _end_document():
        return '</fe:Facturae>'
    
    def _run_java_sign(command):
      #call = [['java','-jar','temp.jar']]
      res = subprocess.call(command,stdout=None,stderr=None)
      if res > 0 :
        print "Warning - result was %d" % res
      return res
    
    def _sign_document(xml_facturae,file_name,invoice):
      path = os.path.realpath(os.path.dirname(__file__))
      path += '/../java/'
      # Almacenamos nuestra cadena XML en un fichero y creamos los ficheros auxiliares.
      file_name_unsigned = path + 'unsigned_' + file_name
      file_name_signed = path + file_name
      file_unsigned = open(file_name_unsigned,"w+")
      file_unsigned.write(xml_facturae)
      file_unsigned.close()      
      file_signed = open(file_name_signed,"w+")
      
      # Extraemos los datos del certificado para la firma electrónica.
      certificate = invoice.company_id.facturae_cert
      cert_passwd = invoice.company_id.facturae_cert_password
      if (not certificate) or (not cert_passwd) :
        log.add(_('User error:\n\nNo se ha seleccionado un certificado electrónico o una clave para la compañía.'), True)
        raise log
      cert_path = path + 'certificado.pfx'
      cert_file = open(cert_path,'wb')
      cert_file.write(certificate.decode('base64'))
      cert_file.close()

      # Componemos la llamada al firmador.
      call = ['java','-jar',path + 'FacturaeJ.jar','0']
      call += [file_name_unsigned,file_name_signed]
      call += ['facturae31']
      call += [cert_path,cert_passwd]
      res = _run_java_sign(call)
      
      # Cerramos y eliminamos ficheros temporales.           
      file_content = file_signed.read()
      file_signed.close()
      os.remove(file_name_unsigned)
      os.remove(file_name_signed)
      os.remove(cert_path)
      
      return file_content

    xml_facturae = ''
    log = Log()
    try:
        pool = pooler.get_pool(cr.dbname)
        invoice = pool.get('account.invoice').browse(cr, uid, data['id'], context)
        contador = 1
        lines_issued = []
        xml_facturae += _format_xml()
        xml_facturae += _header_facturae(cr, context)
        xml_facturae += _parties_facturae(cr, context)
        xml_facturae += _invoices_facturae()
        xml_facturae += _end_document()
        xml_facturae = conv_ascii(xml_facturae)
        # I.AFG
        file_name = (_('facturae') + '_' + invoice.number + '.xsig').replace('/','-')
        signed_invoice = _sign_document(xml_facturae,file_name,invoice)
        #F.AFG
    except Log:
        return {'note':log(), 'reference': 'id', 'facturae':False, 'state':'failed'}
    else:
        
        files = base64.encodestring(signed_invoice)
        fname = (_('facturae') + '_' + invoice.number + '.xsig').replace('/','-')
        pool.get('ir.attachment').create(cr, uid, {
            'name': '%s %s' % (_('FacturaE'), invoice.number),
            'datas': files,
            'datas_fname': fname,
            'res_model': 'account.invoice',
            'res_id': invoice.id,
            }, context=context)
        log.add(_("Export successful\n\nSummary:\nInvoice number: %s\n") % (invoice.number))
        pool.get('account.invoice').set_done(cr,uid,invoice.id,context)

        return {'note':log(), 'reference':invoice.id, 'facturae':files, 'facturae_fname':fname, 'state':'succeeded'}

class wizard_facturae_file(wizard.interface):
    states = {
        'init' : {
            'actions' : [],
            'result' : {'type' : 'form',
                        'arch' : facturae_form,
                        'fields' : facturae_fields,
                        'state' : [('end', 'Cancel'),('export', 'Export','gtk-ok') ]}
        },
        'export': {
            'actions' : [_create_facturae_file],
            'result' : {'type' : 'form',
                        'arch' : export_form,
                        'fields' : export_fields,
                        'state' : [('end', 'Ok','gtk-ok') ]}
        }

    }
wizard_facturae_file('create_facturae_file')

