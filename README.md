# Llego Backend

Backend API for Llego - A comprehensive business management and delivery platform built with FastAPI and GraphQL.

## 🚀 Tech Stack

- **Framework:** FastAPI
- **GraphQL:** Strawberry GraphQL
- **Database:** MongoDB
- **Vector Database:** Qdrant (for semantic search)
- **AI/ML:** Google Gemini (embeddings & chat), DeepSeek (RAG pipeline)
- **Authentication:** Google OAuth, Apple Sign In, JWT
- **Payments:** Stripe
- **Storage:** AWS S3
- **Cache:** Redis
- **Push Notifications:** Apple Push Notification Service (APNs)

## 📋 Features

- GraphQL API with comprehensive schema
- REST endpoints for specific integrations
- Multi-business and multi-branch management
- Product catalog with semantic search
- Order management and tracking
- Payment processing with Stripe
- Wallet system for transactions
- AI-powered chat assistant with RAG
- Push notifications
- Image upload and management
- User authentication and authorization
- Role-based access control (Owner, Manager, Employee)

## 🏗️ Project Structure

```
LlegoBackend/
├── api/                    # REST API endpoints
│   └── endpoints/         # Individual endpoint modules
├── schema/                # GraphQL schema definitions
│   ├── businesses/       # Business-related types, queries, mutations
│   ├── branches/         # Branch management
│   ├── products/         # Product catalog
│   ├── orders/           # Order processing
│   ├── payments/         # Payment handling
│   └── ...
├── services/             # Business logic layer
├── repositories/         # Data access layer
├── domain/               # Pydantic domain models
├── clients/              # External service clients
│   ├── mongodb_client.py
│   ├── qdrant_client.py
│   ├── gemini_client.py
│   └── s3_client.py
├── core/                 # Core configuration
├── utils/                # Utility functions
├── scripts/              # Maintenance and seed scripts
└── main.py              # Application entry point
```

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- MongoDB
- Qdrant (optional, for semantic search)
- Redis (optional, for rate limiting)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd LlegoBackend
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Seed initial data (optional):
```bash
python scripts/seed_business_types.py
python scripts/seed_delivery_zones.py
python scripts/seed_product_categories.py
```

## 🚦 Running the Application

### Development Mode

```bash
python main.py
```

or with uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- GraphQL Playground: `http://localhost:8000/graphql`
- REST API: `http://localhost:8000/api/`
- API Docs: `http://localhost:8000/docs`

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📡 API Endpoints

### GraphQL

- **Endpoint:** `/graphql`
- **Playground:** Available in development mode
- **Schema Download:** `/graphql/schema.graphql`

### REST API

- `/api/users` - User management
- `/api/uploads` - File uploads
- `/api/product-detection` - AI product detection
- `/api/push-notifications` - Push notification management
- `/api/stripe-payments` - Stripe payment webhooks
- `/api/shortcuts` - iOS Shortcuts integration
- `/api/apple-auth` - Apple authentication

## 🔧 Utility Scripts

### Schema Export
```bash
python scripts/export_schema.py
```

### Database Seeding
```bash
python scripts/seed_business_types.py
python scripts/seed_delivery_zones.py
python scripts/seed_product_categories.py
```

### Product Validation
```bash
python scripts/validate_products.py
python scripts/fix_invalid_products.py
```

### Qdrant Maintenance
```bash
python scripts/reindex_businesses_qdrant.py
python scripts/sync_qdrant_mongo_ids.py
python scripts/cleanup_qdrant_duplicates.py
```

### Testing
```bash
python scripts/test_stripe.py
python scripts/test_recharge_link.py
```

## 🔐 Environment Variables

See `.env.example` for all required environment variables. Key configurations include:

- **MongoDB:** Connection string and database name
- **Qdrant:** Vector database configuration
- **Gemini API:** AI and embedding models
- **Authentication:** Google/Apple OAuth credentials
- **Stripe:** Payment processing keys
- **AWS S3:** File storage credentials
- **APNs:** Push notification certificates

## 🏛️ Architecture

### Layered Architecture

1. **API Layer** (`api/`, `schema/`)
   - REST endpoints and GraphQL schema
   - Request validation and response formatting

2. **Service Layer** (`services/`)
   - Business logic
   - Orchestration between repositories
   - Transaction management

3. **Repository Layer** (`repositories/`)
   - Data access abstraction
   - MongoDB operations
   - Qdrant vector operations

4. **Domain Layer** (`domain/`)
   - Pydantic models
   - Business entities
   - Validation rules

5. **Infrastructure Layer** (`clients/`)
   - External service integrations
   - Database connections
   - Third-party APIs

### Key Design Patterns

- **Repository Pattern:** Data access abstraction
- **Dependency Injection:** Service and repository instances
- **Factory Pattern:** Client initialization
- **Singleton Pattern:** Configuration and client instances

## 📝 GraphQL Schema Highlights

### Queries
- `businesses`, `getMyBusinessesWithBranches` - Business management
- `products`, `searchProducts` - Product catalog
- `orders`, `getOrdersByBranch` - Order tracking
- `users`, `getUserProfile` - User management
- `aiChat` - AI assistant interaction

### Mutations
- `registerBusiness`, `updateBusiness` - Business operations
- `createProduct`, `updateProduct` - Product management
- `createOrder`, `updateOrderStatus` - Order processing
- `createPayment`, `processStripePayment` - Payment handling
- `sendBranchInvitation`, `acceptInvitation` - Team management

### Subscriptions
- `orderUpdates` - Real-time order status updates
- `aiChatStream` - Streaming AI responses

## 🤝 Contributing

1. Follow the existing code structure
2. Keep business logic in services
3. Use repositories for data access
4. Add type hints to all functions
5. Document complex logic
6. Test your changes

## 📄 License

[Your License Here]

## 👥 Team

[Your Team Information]
