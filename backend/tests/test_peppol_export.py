import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

from app.services.peppol_export import (
    CAC_NS,
    CBC_NS,
    INVOICE_NS,
    UblInvoice,
    UblLine,
    build_ubl_invoice,
)

NS = {"inv": INVOICE_NS, "cac": CAC_NS, "cbc": CBC_NS}


def _sample() -> UblInvoice:
    return UblInvoice(
        invoice_number="INV-2026-001",
        issue_date=date(2026, 4, 15),
        due_date=date(2026, 5, 31),
        supplier_name="カイケイ商事株式会社",
        customer_name="得意先商店",
        subtotal=Decimal("10000"),
        tax_rate=Decimal("10.00"),
        tax_amount=Decimal("1000"),
        total_amount=Decimal("11000"),
        supplier_registration_number="T1234567890123",
        lines=[
            UblLine("l1", "商品A", Decimal("2"), Decimal("3000"), Decimal("6000")),
            UblLine("l2", "商品B", Decimal("1"), Decimal("4000"), Decimal("4000")),
        ],
    )


class TestBuildUblInvoice:
    def test_wellformed_and_root(self):
        xml = build_ubl_invoice(_sample())
        root = ET.fromstring(xml)
        assert root.tag == f"{{{INVOICE_NS}}}Invoice"

    def test_jp_pint_customization(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        cust = root.find("cbc:CustomizationID", NS)
        assert cust is not None and "jp" in cust.text

    def test_core_header_fields(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        assert root.find("cbc:ID", NS).text == "INV-2026-001"
        assert root.find("cbc:IssueDate", NS).text == "2026-04-15"
        assert root.find("cbc:DocumentCurrencyCode", NS).text == "JPY"
        assert root.find("cbc:InvoiceTypeCode", NS).text == "380"

    def test_supplier_registration_number(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        company_id = root.find(
            "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", NS
        )
        assert company_id is not None and company_id.text == "T1234567890123"

    def test_supplier_and_customer_names(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        s = root.find("cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name", NS)
        c = root.find("cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name", NS)
        assert s.text == "カイケイ商事株式会社"
        assert c.text == "得意先商店"

    def test_line_count_and_amounts(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        lines = root.findall("cac:InvoiceLine", NS)
        assert len(lines) == 2
        assert lines[0].find("cbc:LineExtensionAmount", NS).text == "6000.00"

    def test_totals(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        payable = root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
        assert payable.text == "11000.00"
        assert payable.get("currencyID") == "JPY"

    def test_tax_percent(self):
        root = ET.fromstring(build_ubl_invoice(_sample()))
        pct = root.find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent", NS)
        assert pct.text == "10.00"

    def test_no_registration_number_omits_taxscheme(self):
        inv = _sample()
        inv.supplier_registration_number = None
        root = ET.fromstring(build_ubl_invoice(inv))
        assert root.find("cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme", NS) is None
