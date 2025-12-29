# API de Productos

## Flujo de Imágenes

Para crear o actualizar un producto con imagen:

1. **Subir imagen** via `POST /upload/product/image`
2. **Recibir** `image_path` en la respuesta
3. **Usar** `image_path` en la mutation GraphQL

> Las imágenes de productos preservan transparencia (PNG, WebP). No se convierten a JPG.

---

## Endpoint REST - Upload de Imagen

### Upload Imagen de Producto
```
POST /upload/product/image
Content-Type: multipart/form-data
Authorization: Bearer {jwt}
```

**Form Data:**
- `image`: Archivo de imagen (PNG, JPG, WebP, GIF)

**Response:**
```json
{
  "image_path": "products/6774abc123.png",
  "image_url": "https://s3.../products/6774abc123.png?X-Amz-..."
}
```

---

## Tipo GraphQL

### ProductType
```graphql
type ProductType {
  id: String!
  branchId: String!
  name: String!
  description: String!
  price: Float!
  currency: String!
  weight: String
  image: String
  availability: Boolean!
  categoryId: String
  createdAt: DateTime!
  imageUrl: String       # Presigned URL
}
```

---

## Mutations

### Crear Producto

Se debe proporcionar `branchId` o `businessId` (al menos uno). Si solo se proporciona `businessId`, el producto se asignará a la primera sucursal de ese negocio.

```graphql
mutation CreateProduct($input: CreateProductInput!, $jwt: String) {
  createProduct(input: $input, jwt: $jwt) {
    id
    name
    price
    imageUrl
  }
}
```

**Variables (con branchId):**
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "branchId": "6774branch123",
    "name": "Hamburguesa Clásica",
    "description": "Hamburguesa con queso, lechuga y tomate",
    "price": 15.99,
    "image": "products/6774abc123.png",
    "currency": "USD",
    "weight": "250g",
    "categoryId": "cat_burgers"
  }
}
```

**Variables (con businessId):**
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "businessId": "6774business456",
    "name": "Hamburguesa Clásica",
    "description": "Hamburguesa con queso, lechuga y tomate",
    "price": 15.99,
    "image": "products/6774abc123.png"
  }
}
```

**Response:**
```json
{
  "data": {
    "createProduct": {
      "id": "6774product789",
      "name": "Hamburguesa Clásica",
      "price": 15.99,
      "imageUrl": "https://s3.../products/6774abc123.png?..."
    }
  }
}
```

---

### Actualizar Producto

```graphql
mutation UpdateProduct($productId: String!, $input: UpdateProductInput!, $jwt: String) {
  updateProduct(productId: $productId, input: $input, jwt: $jwt) {
    id
    name
    price
    availability
    imageUrl
  }
}
```

**Variables (actualizar datos):**
```json
{
  "jwt": "eyJhbG...",
  "productId": "6774product789",
  "input": {
    "name": "Hamburguesa Premium",
    "price": 18.99,
    "availability": true
  }
}
```

**Variables (actualizar imagen):**
```json
{
  "jwt": "eyJhbG...",
  "productId": "6774product789",
  "input": {
    "image": "products/new_image_456.png"
  }
}
```

> Al actualizar la imagen, la anterior se elimina automáticamente.

---

### Eliminar Producto

```graphql
mutation DeleteProduct($productId: String!, $jwt: String) {
  deleteProduct(productId: $productId, jwt: $jwt)
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "productId": "6774product789"
}
```

**Response:**
```json
{
  "data": {
    "deleteProduct": true
  }
}
```

---

## Queries

### Obtener Productos

```graphql
query GetProducts($branchId: String, $categoryId: String, $availableOnly: Boolean, $jwt: String) {
  products(branchId: $branchId, categoryId: $categoryId, availableOnly: $availableOnly, jwt: $jwt) {
    id
    name
    description
    price
    currency
    availability
    imageUrl
  }
}
```

**Variables (por sucursal):**
```json
{
  "branchId": "6774branch123"
}
```

**Variables (solo disponibles):**
```json
{
  "availableOnly": true
}
```

---

### Obtener Producto por ID

```graphql
query GetProduct($id: String!, $jwt: String) {
  product(id: $id, jwt: $jwt) {
    id
    name
    description
    price
    currency
    weight
    availability
    categoryId
    imageUrl
    createdAt
  }
}
```

**Variables:**
```json
{
  "id": "6774product789"
}
```

**Response:**
```json
{
  "data": {
    "product": {
      "id": "6774product789",
      "name": "Hamburguesa Clásica",
      "description": "Hamburguesa con queso, lechuga y tomate",
      "price": 15.99,
      "currency": "USD",
      "weight": "250g",
      "availability": true,
      "categoryId": "cat_burgers",
      "imageUrl": "https://s3.../products/6774abc123.png?...",
      "createdAt": "2024-12-29T10:30:00"
    }
  }
}
```

---

### Buscar Productos

```graphql
query SearchProducts($query: String!, $limit: Int, $useVectorSearch: Boolean, $jwt: String) {
  searchProducts(query: $query, limit: $limit, useVectorSearch: $useVectorSearch, jwt: $jwt) {
    id
    name
    price
    imageUrl
  }
}
```

**Variables:**
```json
{
  "query": "hamburguesa",
  "limit": 10,
  "useVectorSearch": true
}
```

---

## Inputs Reference

### CreateProductInput
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| name | String | Sí | Nombre del producto |
| description | String | Sí | Descripción |
| price | Float | Sí | Precio |
| image | String | Sí | Path de imagen (del upload) |
| branchId | String | No* | ID de la sucursal |
| businessId | String | No* | ID del negocio |
| currency | String | No | Moneda (default: "USD") |
| weight | String | No | Peso/porción |
| categoryId | String | No | ID de categoría |

> *Se requiere al menos uno de: `branchId` o `businessId`. Si solo se proporciona `businessId`, el producto se asigna a la primera sucursal del negocio.

### UpdateProductInput
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| name | String | No | Nuevo nombre |
| description | String | No | Nueva descripción |
| price | Float | No | Nuevo precio |
| currency | String | No | Nueva moneda |
| weight | String | No | Nuevo peso |
| availability | Boolean | No | Disponibilidad |
| categoryId | String | No | Nueva categoría |
| image | String | No | Nuevo path de imagen |

---

## Ejemplo Completo: Crear Producto

### Paso 1: Subir Imagen
```bash
curl -X POST "https://api.ejemplo.com/upload/product/image" \
  -H "Authorization: Bearer eyJhbG..." \
  -F "image=@hamburguesa.png"
```

**Response:**
```json
{
  "image_path": "products/6774abc123.png",
  "image_url": "https://s3.../products/6774abc123.png?..."
}
```

### Paso 2: Crear Producto con GraphQL
```graphql
mutation {
  createProduct(
    input: {
      branchId: "6774branch123"
      name: "Hamburguesa Clásica"
      description: "Deliciosa hamburguesa"
      price: 15.99
      image: "products/6774abc123.png"
    }
    jwt: "eyJhbG..."
  ) {
    id
    name
    imageUrl
  }
}
```
