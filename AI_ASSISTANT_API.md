# AI Assistant API Documentation

## Quick Start

**Endpoint**: `POST /graphql`
**Query**: `aiChat(input: {message: String!, deviceId: String}, jwt: String!)`
**Authentication**: JWT required
**Rate Limit**: 2 requests/minute per user
**Response Time**: 2-5 seconds average

## Overview

The AI Assistant API provides an intelligent RAG (Retrieval-Augmented Generation) system for product and store discovery, and order creation. It uses Google Gemini with structured outputs and Qdrant vector search to understand user intent and provide relevant responses.

**What it does**:
- Understands natural language queries about products and stores
- Searches semantic database using embeddings
- Creates draft orders from conversational requests
- Maintains conversation context across messages
- Requests missing information intelligently

## Features

- **Conversation Memory**: Maintains chat history in MongoDB using user ID as session identifier
- **Vector Search**: Searches products, branches, and businesses using semantic similarity
- **Smart Intent Detection**: Automatically determines if user wants to search, create an order, or needs more information
- **Draft Orders**: Creates pending orders that require user confirmation
- **Context-Aware**: Uses conversation history to provide better responses
- **Multi-Step Conversations**: Handles complex interactions across multiple messages
- **Structured Outputs**: Uses Gemini with Pydantic schemas for validated responses

## System Architecture

The AI Assistant uses a two-phase approach:

### Phase 1: Intent Analysis
1. User sends message
2. AI analyzes intent with conversation history
3. Determines response type needed
4. Generates vector search queries (if needed)

### Phase 2: Response Generation
1. Execute vector searches in Qdrant
2. Fetch full entity data from MongoDB
3. AI processes results with metadata
4. Filters irrelevant results
5. Generates final structured response
6. Creates draft order if applicable

**Data Flow**:
```
User Message → GraphQL API → Chat Memory
           ↓
    Intent Analysis (Gemini)
           ↓
    Vector Search (Qdrant) → MongoDB Entities
           ↓
    Final Response (Gemini)
           ↓
    Draft Order Creation (if needed)
           ↓
    GraphQL Response → Frontend
```

## GraphQL API

### Endpoint

```
POST /graphql
```

### Authentication

All requests require JWT authentication. Include the JWT token in the query:

```graphql
query {
  aiChat(input: {...}, jwt: "your_jwt_token") {
    # ...
  }
}
```

### Query: `aiChat`

Send a message to the AI assistant and receive an intelligent response.

#### Input

```graphql
input AiAssistantChatInput {
  message: String!  # The user's message
  deviceId: String  # Mobile device identifier (required for free users)
}
```

### Quota Priority Rules

The backend applies AI quota using this priority order:

1. `user.aiConsultasLimit` (if present):
- `cantidad`: number of allowed queries
- `rango`: `diario | semanal | mensual | por_vida`
2. If no custom limit and user is `isPro = true`: monthly limit from env (`AI_PRO_MONTHLY_LIMIT`)
3. If no custom limit and user is free: lifetime limit per `user + device` from env (`AI_FREE_LIFETIME_LIMIT`)

### Quota Error Codes (GraphQL `errors[].extensions.code`)

- `AI_QUOTA_EXCEEDED`: limit reached for custom limit or pro monthly limit
- `AI_FREE_QUOTA_EXCEEDED`: free lifetime quota reached for `user + device`
- `AI_DEVICE_ID_REQUIRED`: free user request without `deviceId` (and without `x-device-id` header)

When quota fails, backend also returns `errors[].extensions.quota`:
- `source`
- `limit`
- `used`
- `remaining`

#### Response

```graphql
type AiAssistantResponseType {
  responseType: String!  # Type of response (see below)
  aiText: String!  # Natural language response from AI
  suggestedProducts: [ProductSuggestionType!]!  # Products suggested by AI
  suggestedBranches: [BranchSuggestionType!]!  # Stores/branches suggested
  draftOrder: DraftOrderType  # Draft order if created
  missingFields: [String!]!  # Fields AI needs from user
  confidence: Float!  # AI confidence (0.0 to 1.0)
}
```

#### Response Types

- `search_products`: AI found relevant products for user's query
- `search_branches`: AI found relevant stores/branches
- `create_draft_order`: AI created a draft order (needs confirmation)
- `request_details`: AI needs more information (delivery address, payment method, etc.)
- `general_response`: General conversation

#### Nested Types

```graphql
type ProductSuggestionType {
  product: ProductType!  # Full product details
  reason: String!  # Why this product was suggested
}

type BranchSuggestionType {
  branch: BranchType!  # Full branch details
  reason: String!  # Why this branch was suggested
}

type DraftOrderType {
  id: String!
  sessionId: String!
  customerId: String!
  branchId: String!
  businessId: String!
  items: [DraftOrderItemType!]!
  subtotal: Float!
  deliveryFee: Float!
  total: Float!
  currency: String!
  deliveryAddress: String
  paymentMethodId: String
  status: String!
  createdAt: DateTime!
  expiresAt: DateTime!  # Expires in 1 hour
}

type DraftOrderItemType {
  productId: String!
  name: String!
  price: Float!
  quantity: Int!
  imageUrl: String!
}
```

## Usage Examples

### Example 1: Search for Products

**Request:**
```graphql
query {
  aiChat(
    input: { message: "I'm looking for pizza" }
    jwt: "eyJhbGciOiJIUzI1NiIs..."
  ) {
    responseType
    aiText
    suggestedProducts {
      product {
        id
        name
        price
        currency
        image
        availability
      }
      reason
    }
    confidence
  }
}
```

**Response:**
```json
{
  "data": {
    "aiChat": {
      "responseType": "search_products",
      "aiText": "I found 5 pizza options for you. The Margherita Pizza is a classic choice, and the Pepperoni Pizza is very popular.",
      "suggestedProducts": [
        {
          "product": {
            "id": "507f1f77bcf86cd799439011",
            "name": "Margherita Pizza",
            "price": 12.99,
            "currency": "USD",
            "image": "https://...",
            "availability": true
          },
          "reason": "Classic pizza with fresh mozzarella and basil"
        },
        {
          "product": {
            "id": "507f1f77bcf86cd799439012",
            "name": "Pepperoni Pizza",
            "price": 14.99,
            "currency": "USD",
            "image": "https://...",
            "availability": true
          },
          "reason": "Popular choice with spicy pepperoni"
        }
      ],
      "suggestedBranches": [],
      "draftOrder": null,
      "missingFields": [],
      "confidence": 0.92
    }
  }
}
```

### Example 2: Search for Stores

**Request:**
```graphql
query {
  aiChat(
    input: { message: "Show me Italian restaurants nearby" }
    jwt: "eyJhbGciOiJIUzI1NiIs..."
  ) {
    responseType
    aiText
    suggestedBranches {
      branch {
        id
        name
        address
        tipos
        coordinates {
          type
          coordinates
        }
      }
      reason
    }
  }
}
```

**Response:**
```json
{
  "data": {
    "aiChat": {
      "responseType": "search_branches",
      "aiText": "Here are 3 Italian restaurants I found near you:",
      "suggestedProducts": [],
      "suggestedBranches": [
        {
          "branch": {
            "id": "507f1f77bcf86cd799439013",
            "name": "Bella Italia",
            "address": "123 Main St",
            "tipos": ["restaurante"],
            "coordinates": {
              "type": "Point",
              "coordinates": [-73.935242, 40.730610]
            }
          },
          "reason": "Authentic Italian restaurant with 4.5 star rating"
        }
      ],
      "draftOrder": null,
      "missingFields": [],
      "confidence": 0.88
    }
  }
}
```

### Example 3: Create Draft Order

**Request (user has provided all details in conversation):**
```graphql
query {
  aiChat(
    input: {
      message: "I want to order 2 Margherita pizzas to 123 Main St, paying with cash"
    }
    jwt: "eyJhbGciOiJIUzI1NiIs..."
  ) {
    responseType
    aiText
    draftOrder {
      id
      branchId
      items {
        productId
        name
        price
        quantity
      }
      subtotal
      deliveryFee
      total
      deliveryAddress
      status
      expiresAt
    }
    confidence
  }
}
```

**Response:**
```json
{
  "data": {
    "aiChat": {
      "responseType": "create_draft_order",
      "aiText": "Great! I've created your order for 2 Margherita pizzas. The total is $30.98 including delivery. Please confirm to proceed.",
      "suggestedProducts": [],
      "suggestedBranches": [],
      "draftOrder": {
        "id": "507f1f77bcf86cd799439014",
        "branchId": "507f1f77bcf86cd799439013",
        "items": [
          {
            "productId": "507f1f77bcf86cd799439011",
            "name": "Margherita Pizza",
            "price": 12.99,
            "quantity": 2
          }
        ],
        "subtotal": 25.98,
        "deliveryFee": 5.00,
        "total": 30.98,
        "deliveryAddress": "123 Main St",
        "status": "pending_confirmation",
        "expiresAt": "2026-01-27T15:30:00Z"
      },
      "missingFields": [],
      "confidence": 0.95
    }
  }
}
```

### Example 4: AI Requests Missing Information

**Request:**
```graphql
query {
  aiChat(
    input: { message: "I want to order pizza" }
    jwt: "eyJhbGciOiJIUzI1NiIs..."
  ) {
    responseType
    aiText
    missingFields
    suggestedProducts {
      product {
        id
        name
        price
      }
      reason
    }
  }
}
```

**Response:**
```json
{
  "data": {
    "aiChat": {
      "responseType": "request_details",
      "aiText": "I found several pizza options for you! Which one would you like? Also, I'll need your delivery address and preferred payment method.",
      "suggestedProducts": [
        {
          "product": {
            "id": "507f1f77bcf86cd799439011",
            "name": "Margherita Pizza",
            "price": 12.99
          },
          "reason": "Classic option"
        }
      ],
      "suggestedBranches": [],
      "draftOrder": null,
      "missingFields": [
        "selected_product",
        "delivery_address",
        "payment_method"
      ],
      "confidence": 0.87
    }
  }
}
```

## Frontend Integration Guide

### 1. GraphQL Client Setup

Configure your GraphQL client to connect to the API endpoint:
- **Endpoint**: `POST /graphql`
- **Headers**: Include JWT token for authentication
- **Cache**: Enable for better performance

### 2. AI Chat GraphQL Query

Use this query to send messages to the AI assistant:

```graphql
query AiChat($message: String!, $jwt: String!) {
  aiChat(input: { message: $message }, jwt: $jwt) {
    responseType
    aiText
    suggestedProducts {
      product {
        id
        name
        price
        currency
        image
        availability
      }
      reason
    }
    suggestedBranches {
      branch {
        id
        name
        address
        tipos
        coordinates {
          type
          coordinates
        }
      }
      reason
    }
    draftOrder {
      id
      items {
        productId
        name
        price
        quantity
        imageUrl
      }
      subtotal
      deliveryFee
      total
      deliveryAddress
      paymentMethodId
      status
      expiresAt
    }
    missingFields
    confidence
  }
}
```

### 3. Client-Side Chat Management

Your frontend should maintain:

**Chat History**:
- Store messages locally (array of `{role: string, content: string}`)
- Role can be "user" or "assistant"
- Display messages in chronological order

**Message Flow**:
1. User types message and submits
2. Add user message to local history
3. Send GraphQL query with message and JWT
4. Receive AI response
5. Add AI response (`aiText`) to local history
6. Handle specific response type (see next section)

### 4. Handling Response Types

Based on `responseType`, show different UI:

**`search_products`**:
- Display suggested products grid/list
- Show product image, name, price
- Include AI's `reason` for each suggestion
- Allow user to add to cart or order

**`search_branches`**:
- Display suggested stores/branches
- Show store name, address, types
- Include AI's `reason` for each suggestion
- Show on map if coordinates available
- Allow user to select a store

**`create_draft_order`**:
- Show order summary/confirmation screen
- Display all items with quantities and prices
- Show delivery address and payment method
- Display subtotal, delivery fee, and total
- Show expiration time (1 hour from creation)
- Provide "Confirm Order" and "Cancel" buttons

**`request_details`**:
- Check `missingFields` array
- Show form to collect missing information
- Common fields: `delivery_address`, `payment_method`, `selected_product`
- After collecting info, send as new message

**`general_response`**:
- Simply display `aiText` as chat message
- No special UI needed

### 5. UI Best Practices

**Loading States**:
- Show loading indicator while waiting for AI response (2-5 seconds typical)
- Disable input while processing
- Consider showing typing indicator

**Confidence Display**:
- Use `confidence` score (0.0 to 1.0) to indicate AI certainty
- Optional: Show low confidence warning if < 0.7

**Draft Order Handling**:
- Display countdown timer for 1-hour expiration
- Store draft order ID for confirmation
- Clear draft from UI after expiration or cancellation

**Error Handling**:
- Handle null responses gracefully
- Show user-friendly error messages
- Allow retry on network errors

**Product/Branch Display**:
- Show `reason` as tooltip or subtitle
- Highlight suggested items visually
- Allow filtering or sorting results

## Conversation Flow Example

### Multi-turn Conversation

The AI maintains context across messages. Here's a typical flow:

**Turn 1:**
```
User: "I want pizza"
AI: "I found several pizza options for you! Here are the most popular ones..."
Response Type: search_products
Suggested Products: [Margherita, Pepperoni, ...]
```

**Turn 2:**
```
User: "I'll take the Margherita, 2 pieces"
AI: "Great choice! To complete your order, I need your delivery address and payment method."
Response Type: request_details
Missing Fields: ["delivery_address", "payment_method"]
```

**Turn 3:**
```
User: "Deliver to 123 Main St, I'll pay with cash"
AI: "Perfect! I've created your order for 2 Margherita pizzas..."
Response Type: create_draft_order
Draft Order: {...}
```

## Error Handling

Handle errors appropriately in your client:

**GraphQL Errors**:
- Network failures
- Invalid queries
- Authentication errors (invalid JWT)
- Rate limiting exceeded

**Null Response** (`aiChat` returns `null`):
- AI service temporarily unavailable
- Internal server error
- Error will be logged on backend

**User Messages**:
- "Failed to send message. Please try again."
- "AI is temporarily unavailable. Please try again later."
- "You've exceeded the rate limit. Please wait a moment."

## Rate Limiting

- **Limit**: 2 requests per minute per user
- **Reason**: Gemini API calls are expensive
- If rate limit is exceeded, the API will return an error

## Implementation Best Practices

1. **Show Loading State**: AI responses can take 2-5 seconds - always show visual feedback
2. **Display Confidence**: Use the `confidence` score (0.0-1.0) to indicate AI certainty to users
3. **Handle Draft Orders**: Draft orders expire after 1 hour - show countdown timer
4. **Validate Missing Fields**: Show appropriate forms/dialogs for collecting missing information
5. **Product Validation**: Ensure all products in an order are from the same branch (backend validates this too)
6. **Context Awareness**: The AI uses last 10 messages for context - no need to send full history
7. **Preserve History**: Store conversation history locally for better UX
8. **Graceful Degradation**: Handle null responses and errors without breaking the UI
9. **Security**: Never expose JWT tokens in logs or error messages
10. **Accessibility**: Ensure chat interface is keyboard navigable and screen-reader friendly

## Session Management

- Sessions are identified by user ID from JWT
- Chat history persists in MongoDB
- History can be cleared via backend (future feature)
- Old messages (>30 days) are automatically cleaned up

## Database Collections

The AI Assistant uses these MongoDB collections:

- `chat_messages`: Conversation history
- `draft_orders`: Pending orders awaiting confirmation

## Vector Search Collections (Qdrant)

- `products`: Product embeddings for semantic search
- `branches`: Branch/store embeddings
- `businesses`: Business embeddings

## Confirming Draft Orders

When AI creates a draft order (`create_draft_order` response type), the order is NOT final. It's pending user confirmation.

**Draft Order Workflow**:
1. AI creates draft order in database (status: `pending_confirmation`)
2. Frontend receives draft order data
3. Show user confirmation UI with all details
4. User confirms or cancels
5. If confirmed: Create actual order using existing order creation mutation
6. If cancelled or expired: Draft is deleted automatically

**Important**: Draft orders are just proposals. To create the actual order, you must:
- Use your existing order creation mutation/endpoint
- Pass the draft order details (items, delivery address, payment method, etc.)
- The draft order provides pre-filled data, not the final order

## Data Types Reference

### Response Type Values

- `search_products`: Product search results
- `search_branches`: Store/branch search results
- `create_draft_order`: Draft order created (pending confirmation)
- `request_details`: AI needs more info from user
- `general_response`: General conversation

### Missing Fields Values

When `response_type` is `request_details`, check `missingFields` for:
- `delivery_address`: Need delivery address
- `payment_method`: Need payment method selection
- `selected_product`: Need product selection
- `quantity`: Need product quantity
- `branch_selection`: Need store/branch selection

## Notes

- All products in a draft order must be from the same branch
- Draft orders expire after 1 hour and are auto-deleted
- The AI uses conversation history (last 10 messages) for context
- Vector search uses Gemini embeddings for semantic similarity
- Session is tied to user ID from JWT - one conversation per user
- No manual session management needed on frontend
