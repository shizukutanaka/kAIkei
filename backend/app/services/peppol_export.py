"""Peppol / JP PINT デジタルインボイス（UBL 2.1）エクスポート（フェーズ3）。

請求書を Peppol BIS Billing 3.0（日本標準仕様 JP PINT）準拠の UBL Invoice XML に
変換する。生成の中核はDB非依存の純粋関数として切り出し、単体テスト可能にする。

（Peppolネットワークへの実送信はアクセスポイント契約が必要なため別途。）
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# UBL 2.1 名前空間。
INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# JP PINT（日本のPeppol標準仕様）。
CUSTOMIZATION_ID = "urn:peppol:pint:billing-1@jp-1"
PROFILE_ID = "urn:peppol:bis:billing"
INVOICE_TYPE_CODE = "380"  # 商業請求書

ET.register_namespace("", INVOICE_NS)
ET.register_namespace("cac", CAC_NS)
ET.register_namespace("cbc", CBC_NS)


@dataclass
class UblLine:
    line_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass
class UblInvoice:
    invoice_number: str
    issue_date: date
    due_date: date
    supplier_name: str
    customer_name: str
    subtotal: Decimal
    tax_rate: Decimal  # 百分率（例: 10.00）
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[UblLine] = field(default_factory=list)
    currency: str = "JPY"
    supplier_registration_number: str | None = None


def _money(value: Decimal) -> str:
    """UBL金額表現（小数2桁）に整形する。"""
    return f"{Decimal(value):.2f}"


def _cbc(parent: ET.Element, tag: str, text: str, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{CBC_NS}}}{tag}", attrs)
    el.text = text
    return el


def _cac(parent: ET.Element, tag: str) -> ET.Element:
    return ET.SubElement(parent, f"{{{CAC_NS}}}{tag}")


def build_ubl_invoice(inv: UblInvoice) -> str:
    """UblInvoiceからPeppol BIS/JP PINT準拠のUBL Invoice XML文字列を生成する。"""
    root = ET.Element(f"{{{INVOICE_NS}}}Invoice")

    _cbc(root, "CustomizationID", CUSTOMIZATION_ID)
    _cbc(root, "ProfileID", PROFILE_ID)
    _cbc(root, "ID", inv.invoice_number)
    _cbc(root, "IssueDate", inv.issue_date.isoformat())
    _cbc(root, "DueDate", inv.due_date.isoformat())
    _cbc(root, "InvoiceTypeCode", INVOICE_TYPE_CODE)
    _cbc(root, "DocumentCurrencyCode", inv.currency)

    # 供給者（自社）
    supplier = _cac(root, "AccountingSupplierParty")
    s_party = _cac(supplier, "Party")
    s_name = _cac(s_party, "PartyName")
    _cbc(s_name, "Name", inv.supplier_name)
    if inv.supplier_registration_number:
        tax_scheme = _cac(s_party, "PartyTaxScheme")
        _cbc(tax_scheme, "CompanyID", inv.supplier_registration_number)
        scheme = _cac(tax_scheme, "TaxScheme")
        _cbc(scheme, "ID", "VAT")

    # 顧客（取引先）
    customer = _cac(root, "AccountingCustomerParty")
    c_party = _cac(customer, "Party")
    c_name = _cac(c_party, "PartyName")
    _cbc(c_name, "Name", inv.customer_name)

    # 税額合計
    tax_total = _cac(root, "TaxTotal")
    _cbc(tax_total, "TaxAmount", _money(inv.tax_amount), currencyID=inv.currency)
    subtotal_el = _cac(tax_total, "TaxSubtotal")
    _cbc(subtotal_el, "TaxableAmount", _money(inv.subtotal), currencyID=inv.currency)
    _cbc(subtotal_el, "TaxAmount", _money(inv.tax_amount), currencyID=inv.currency)
    tax_cat = _cac(subtotal_el, "TaxCategory")
    _cbc(tax_cat, "ID", "S")
    _cbc(tax_cat, "Percent", f"{Decimal(inv.tax_rate):.2f}")
    cat_scheme = _cac(tax_cat, "TaxScheme")
    _cbc(cat_scheme, "ID", "VAT")

    # 合計金額
    totals = _cac(root, "LegalMonetaryTotal")
    _cbc(totals, "LineExtensionAmount", _money(inv.subtotal), currencyID=inv.currency)
    _cbc(totals, "TaxExclusiveAmount", _money(inv.subtotal), currencyID=inv.currency)
    _cbc(totals, "TaxInclusiveAmount", _money(inv.total_amount), currencyID=inv.currency)
    _cbc(totals, "PayableAmount", _money(inv.total_amount), currencyID=inv.currency)

    # 明細
    for i, line in enumerate(inv.lines, start=1):
        line_el = _cac(root, "InvoiceLine")
        _cbc(line_el, "ID", str(i))
        _cbc(line_el, "InvoicedQuantity", f"{Decimal(line.quantity):.3f}", unitCode="C62")
        _cbc(line_el, "LineExtensionAmount", _money(line.line_total), currencyID=inv.currency)
        item = _cac(line_el, "Item")
        _cbc(item, "Name", line.description)
        price = _cac(line_el, "Price")
        _cbc(price, "PriceAmount", _money(line.unit_price), currencyID=inv.currency)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
