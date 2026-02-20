"""Pydantic schemas for validating LLM extraction output."""

from pydantic import BaseModel, field_validator


class PricingItem(BaseModel):
    """A single pricing line item extracted by the LLM."""

    size: str
    grade: str
    quantity_kg: float
    price_per_kg: float

    @field_validator("quantity_kg", "price_per_kg")
    @classmethod
    def must_be_positive(cls, v: float, info) -> float:
        if v < 0:
            raise ValueError(f"{info.field_name} must be non-negative, got {v}")
        return v


class PricingExtraction(BaseModel):
    """Top-level extraction result from the LLM."""

    supplier: str
    currency: str
    total_kg: float
    items: list[PricingItem]
    confidence: float

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[PricingItem]) -> list[PricingItem]:
        if not v:
            raise ValueError("items array must not be empty")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {v}")
        return v

    def check_total_kg_consistency(self, tolerance: float = 0.1) -> bool:
        """Optional check: total_kg ≈ sum of item quantities.

        Returns True if consistent, False otherwise.
        Uses relative tolerance.
        """
        items_sum = sum(item.quantity_kg for item in self.items)
        if items_sum == 0:
            return self.total_kg == 0
        ratio = abs(self.total_kg - items_sum) / items_sum
        return ratio <= tolerance
