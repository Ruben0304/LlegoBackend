"""Tests for combo pricing calculations."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from schema.combos.types import ComboType, ComboSlotType, ComboOptionType, ComboModifierType, DiscountType
from datetime import datetime


@pytest.fixture
def mock_products_repo(monkeypatch):
    """Mock products repository for testing."""
    from repositories import products_repo
    
    # Mock products with different prices
    mock_products = {
        "product1": MagicMock(id="product1", price=10.0),
        "product2": MagicMock(id="product2", price=15.0),
        "product3": MagicMock(id="product3", price=20.0),
        "product4": MagicMock(id="product4", price=8.0),
        "product5": MagicMock(id="product5", price=12.0),
    }
    
    async def mock_get_by_id(product_id: str):
        return mock_products.get(product_id)
    
    monkeypatch.setattr(products_repo, "get_by_id", mock_get_by_id)
    return mock_products


@pytest.mark.asyncio
async def test_starting_base_price_simple_combo(mock_products_repo):
    """Test starting_base_price with a simple combo (1 product per slot)."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                    ComboOptionType(
                        productId="product2",  # $15
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
            ComboSlotType(
                id="slot2",
                name="Side",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product4",  # $8
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                    ComboOptionType(
                        productId="product5",  # $12
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=2
            ),
        ],
        discountType=DiscountType.NONE,
        discountValue=0.0,
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Should pick cheapest from each slot: product1 ($10) + product4 ($8) = $18
    base_price = await combo.starting_base_price(info)
    assert base_price == 18.0


@pytest.mark.asyncio
async def test_starting_base_price_with_price_adjustment(mock_products_repo):
    """Test starting_base_price with priceAdjustment."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10 + $2 = $12
                        isDefault=True,
                        priceAdjustment=2.0,
                        availableModifiers=[]
                    ),
                    ComboOptionType(
                        productId="product2",  # $15 + $0 = $15
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
        ],
        discountType=DiscountType.NONE,
        discountValue=0.0,
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Should pick cheapest: product1 with adjustment ($10 + $2 = $12)
    base_price = await combo.starting_base_price(info)
    assert base_price == 12.0


@pytest.mark.asyncio
async def test_starting_base_price_optional_slot(mock_products_repo):
    """Test that optional slots (minSelections=0) are not included in starting price."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
            ComboSlotType(
                id="slot2",
                name="Optional Extra",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product4",  # $8 (should NOT be included)
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=0,  # Optional!
                maxSelections=1,
                isRequired=False,
                displayOrder=2
            ),
        ],
        discountType=DiscountType.NONE,
        discountValue=0.0,
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Should only include slot1: $10
    base_price = await combo.starting_base_price(info)
    assert base_price == 10.0


@pytest.mark.asyncio
async def test_starting_final_price_with_percentage_discount(mock_products_repo):
    """Test starting_final_price with percentage discount."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
        ],
        discountType=DiscountType.PERCENTAGE,
        discountValue=20.0,  # 20% off
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Base: $10, 20% off = $8
    final_price = await combo.starting_final_price(info)
    assert final_price == 8.0


@pytest.mark.asyncio
async def test_starting_final_price_with_fixed_discount(mock_products_repo):
    """Test starting_final_price with fixed discount."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
        ],
        discountType=DiscountType.FIXED,
        discountValue=3.0,  # $3 off
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Base: $10, $3 off = $7
    final_price = await combo.starting_final_price(info)
    assert final_price == 7.0


@pytest.mark.asyncio
async def test_starting_savings(mock_products_repo):
    """Test starting_savings calculation."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Main",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=1,
                maxSelections=1,
                isRequired=True,
                displayOrder=1
            ),
        ],
        discountType=DiscountType.PERCENTAGE,
        discountValue=25.0,  # 25% off
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Base: $10, Final: $7.50, Savings: $2.50
    savings = await combo.starting_savings(info)
    assert savings == 2.5


@pytest.mark.asyncio
async def test_starting_base_price_multiple_selections(mock_products_repo):
    """Test starting_base_price when minSelections > 1."""
    combo = ComboType(
        id="combo1",
        branchId="branch1",
        name="Test Combo",
        description="Test",
        image=None,
        slots=[
            ComboSlotType(
                id="slot1",
                name="Choose 2 Sides",
                description=None,
                options=[
                    ComboOptionType(
                        productId="product1",  # $10
                        isDefault=True,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                    ComboOptionType(
                        productId="product4",  # $8
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                    ComboOptionType(
                        productId="product5",  # $12
                        isDefault=False,
                        priceAdjustment=0.0,
                        availableModifiers=[]
                    ),
                ],
                minSelections=2,  # Must select 2
                maxSelections=2,
                isRequired=True,
                displayOrder=1
            ),
        ],
        discountType=DiscountType.NONE,
        discountValue=0.0,
        currency="USD",
        availability=True,
        categoryId=None,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    
    info = MagicMock()
    
    # Should pick 2 cheapest: product4 ($8) + product1 ($10) = $18
    base_price = await combo.starting_base_price(info)
    assert base_price == 18.0
