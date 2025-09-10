from pydantic import BaseModel
from typing import List


# Data models
class Store(BaseModel):
    id: int
    name: str
    etaMinutes: int
    logoUrl: str
    bannerUrl: str


class Product(BaseModel):
    id: int
    name: str
    shop: str
    weight: str
    price: str
    imageUrl: str


# In-memory repositories with sample data
class StoreRepository:
    def get_stores(self) -> List[Store]:
        return [
            Store(
                id=1,
                name="T&T Food Market",
                etaMinutes=12,
                logoUrl="https://images.unsplash.com/photo-1606813907291-fc2d69fce182?w=200&h=200&fit=crop",
                bannerUrl="https://images.unsplash.com/photo-1600891964599-f61ba0e24092?w=800&h=400&fit=crop",
            ),
            Store(
                id=2,
                name="Backend Market",
                etaMinutes=8,
                logoUrl="https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=200&h=200&fit=crop",
                bannerUrl="https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&h=400&fit=crop",
            ),
            Store(
                id=3,
                name="Organic Valley",
                etaMinutes=15,
                logoUrl="https://images.unsplash.com/photo-1607631568010-a87245c0daf8?w=200&h=200&fit=crop",
                bannerUrl="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=400&fit=crop",
            ),
            Store(
                id=4,
                name="Green Corner",
                etaMinutes=20,
                logoUrl="https://images.unsplash.com/photo-1599481238505-461a2d3d2b58?w=200&h=200&fit=crop",
                bannerUrl="https://images.unsplash.com/photo-1555992336-03a23c0b3e0e?w=800&h=400&fit=crop",
            ),
            Store(
                id=5,
                name="Local Deli",
                etaMinutes=6,
                logoUrl="https://images.unsplash.com/photo-1472851294608-062f824d29cc?w=200&h=200&fit=crop",
                bannerUrl="https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&h=400&fit=crop",
            ),
        ]


class ProductRepository:
    def get_products(self) -> List[Product]:
        return [
            Product(
                id=1,
                name="Beetroot",
                shop="Local Shop",
                weight="500 gm.",
                price="17.29$",
                imageUrl="https://images.unsplash.com/photo-1570197788417-0e82375c9371?w=300",
            ),
            Product(
                id=2,
                name="Italian Avocado",
                shop="Fresh Market",
                weight="450 gm.",
                price="14.29$",
                imageUrl="https://images.unsplash.com/photo-1523049673857-eb18f1d7b578?w=300",
            ),
            Product(
                id=3,
                name="Red Tomatoes",
                shop="Garden Fresh",
                weight="1 kg.",
                price="8.50$",
                imageUrl="https://images.unsplash.com/photo-1546470427-e26264be0b0d?w=300",
            ),
            Product(
                id=4,
                name="Green Broccoli",
                shop="Organic Store",
                weight="750 gm.",
                price="12.99$",
                imageUrl="https://images.unsplash.com/photo-1459411621453-7b03977f4bfc?w=300",
            ),
            Product(
                id=5,
                name="Yellow Bell Pepper",
                shop="Local Shop",
                weight="300 gm.",
                price="6.75$",
                imageUrl="https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?w=300",
            ),
            Product(
                id=6,
                name="Fresh Carrots",
                shop="Farm Direct",
                weight="1 kg.",
                price="5.99$",
                imageUrl="https://images.unsplash.com/photo-1445282768818-728615cc910a?w=300",
            ),
            Product(
                id=7,
                name="Purple Cabbage",
                shop="Organic Store",
                weight="800 gm.",
                price="9.25$",
                imageUrl="https://images.unsplash.com/photo-1594282486552-05b4d80fbb9f?w=300",
            ),
            Product(
                id=8,
                name="Sweet Corn",
                shop="Garden Fresh",
                weight="4 pieces",
                price="7.50$",
                imageUrl="https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=300",
            ),
            Product(
                id=9,
                name="Red Onions",
                shop="Local Shop",
                weight="1 kg.",
                price="4.99$",
                imageUrl="https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=300",
            ),
            Product(
                id=10,
                name="Fresh Spinach",
                shop="Organic Store",
                weight="250 gm.",
                price="3.75$",
                imageUrl="https://images.unsplash.com/photo-1576045057995-568f588f82fb?w=300",
            ),
            Product(
                id=11,
                name="Green Cucumber",
                shop="Fresh Market",
                weight="500 gm.",
                price="4.25$",
                imageUrl="https://images.unsplash.com/photo-1449300079323-02e209d9d3a6?w=300",
            ),
            Product(
                id=12,
                name="Orange Pumpkin",
                shop="Farm Direct",
                weight="2 kg.",
                price="11.99$",
                imageUrl="https://images.unsplash.com/photo-1570586437263-ab629fccc818?w=300",
            ),
        ]


# Singletons for convenience
stores_repo = StoreRepository()
products_repo = ProductRepository()
