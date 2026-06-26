from decimal import ROUND_DOWN, Decimal


class TaxCalculator:
    """Tax calculation engine for Japanese consumption tax."""

    @staticmethod
    def calculate_tax(amount: Decimal, tax_rate: Decimal, is_inclusive: bool) -> tuple[Decimal, Decimal]:
        """Calculate tax amount and tax-excluded amount.

        Args:
            amount: The input amount (tax-included if is_inclusive, tax-excluded otherwise)
            tax_rate: Tax rate as a decimal (e.g., 0.10 for 10%)
            is_inclusive: Whether the amount includes tax

        Returns:
            Tuple of (tax_excluded_amount, tax_amount)
        """
        if is_inclusive:
            tax_excluded = (amount / (Decimal("1") + tax_rate)).quantize(Decimal("1"), rounding=ROUND_DOWN)
            tax_amount = amount - tax_excluded
        else:
            tax_amount = (amount * tax_rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
            tax_excluded = amount

        return tax_excluded, tax_amount

    @staticmethod
    def calculate_inclusive_10(amount: Decimal) -> tuple[Decimal, Decimal]:
        """10% inclusive tax calculation."""
        return TaxCalculator.calculate_tax(amount, Decimal("0.10"), is_inclusive=True)

    @staticmethod
    def calculate_exclusive_10(amount: Decimal) -> tuple[Decimal, Decimal]:
        """10% exclusive tax calculation."""
        return TaxCalculator.calculate_tax(amount, Decimal("0.10"), is_inclusive=False)

    @staticmethod
    def calculate_inclusive_8(amount: Decimal) -> tuple[Decimal, Decimal]:
        """8% inclusive tax calculation (reduced rate)."""
        return TaxCalculator.calculate_tax(amount, Decimal("0.08"), is_inclusive=True)

    @staticmethod
    def calculate_exclusive_8(amount: Decimal) -> tuple[Decimal, Decimal]:
        """8% exclusive tax calculation (reduced rate)."""
        return TaxCalculator.calculate_tax(amount, Decimal("0.08"), is_inclusive=False)
