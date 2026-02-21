"""Pydantic schemas for validating LLM extraction output."""

from pydantic import BaseModel, field_validator


class PricingItem(BaseModel):
    """A single pricing line item extracted by the LLM."""

    size: str | None = None
    grade: str | None = None
    quantity_kg: float | None = None
    price_per_kg: float | None = None

    @field_validator("quantity_kg", "price_per_kg")
    @classmethod
    def must_be_positive(cls, v: float | None, info) -> float | None:
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} must be non-negative, got {v}")
        return v

    def is_complete(self) -> bool:
        """Return True if the item has enough data to be useful."""
        return self.price_per_kg is not None and (
            self.quantity_kg is not None or self.size is not None
        )


class Offer(BaseModel):
    """A single pricing offer from one supplier."""

    supplier: str | None = None
    product: str | None = None
    currency: str | None = None
    total_kg: float | None = None
    items: list[PricingItem] = []

    def complete_items(self) -> list[PricingItem]:
        """Return only items with enough data to persist."""
        return [item for item in self.items if item.is_complete()]

    def check_total_kg_consistency(self, tolerance: float = 0.1) -> bool:
        """Check: total_kg ≈ sum of item quantities.

        Returns True if consistent or total_kg is None.
        """
        if self.total_kg is None:
            return True
        complete = self.complete_items()
        items_sum = sum(item.quantity_kg for item in complete if item.quantity_kg)
        if items_sum == 0:
            return self.total_kg == 0
        ratio = abs(self.total_kg - items_sum) / items_sum
        return ratio <= tolerance


class PricingExtraction(BaseModel):
    """Top-level extraction result from the LLM."""

    offers: list[Offer] = []
    confidence: float

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {v}")
        return v

    def has_actionable_data(self) -> bool:
        """Return True if at least one offer has complete items."""
        return any(offer.complete_items() for offer in self.offers)
