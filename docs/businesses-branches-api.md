# API de Negocios y Sucursales

## Flujo de Imágenes

Para cualquier operación que incluya imágenes (avatar, cover):

1. **Subir imagen** via REST endpoint
2. **Recibir** `image_path` en la respuesta
3. **Usar** `image_path` en la mutation GraphQL

---

## Endpoints REST - Upload de Imágenes

### Upload Avatar de Negocio
```
POST /upload/business/avatar
Content-Type: multipart/form-data
Authorization: Bearer {jwt}
```

**Form Data:**
- `image`: Archivo de imagen

**Response:**
```json
{
  "image_path": "businesses/avatars/6774abc123.jpg",
  "image_url": "https://s3.../businesses/avatars/6774abc123.jpg?X-Amz-..."
}
```

### Upload Cover de Negocio
```
POST /upload/business/cover
Authorization: Bearer {jwt}
```

### Upload Avatar de Sucursal
```
POST /upload/branch/avatar
Authorization: Bearer {jwt}
```

### Upload Cover de Sucursal
```
POST /upload/branch/cover
Authorization: Bearer {jwt}
```

> Las imágenes de negocios/sucursales se convierten a JPG y se redimensionan automáticamente.

---

## Tipos GraphQL

### BusinessType
```graphql
type BusinessType {
  id: String!
  name: String!
  type: String!
  ownerId: String!
  globalRating: Float!
  avatar: String
  coverImage: String
  description: String
  socialMedia: JSON
  tags: [String!]!
  isActive: Boolean!
  createdAt: DateTime!
  avatarUrl: String      # Presigned URL
  coverUrl: String       # Presigned URL
}
```

### BranchType
```graphql
type BranchType {
  id: String!
  businessId: String!
  name: String!
  address: String
  coordinates: CoordinatesType!
  phone: String!
  schedule: JSON!
  managerIds: [String!]!
  status: String!
  avatar: String
  coverImage: String
  deliveryRadius: Float
  facilities: [String!]!
  createdAt: DateTime!
  avatarUrl: String      # Presigned URL
  coverUrl: String       # Presigned URL
}

type CoordinatesType {
  type: String!
  coordinates: [Float!]!  # [lng, lat]
}
```

---

## Mutations

### Registrar Negocio con Sucursales

> **Nota**: Al registrar un negocio exitosamente, el `businessId` se agrega automáticamente a la lista `businessIds` del usuario autenticado.

```graphql
mutation RegisterBusiness($business: CreateBusinessInput!, $branches: [RegisterBranchInput!]!, $jwt: String) {
  registerBusiness(businessInput: $business, branchesInput: $branches, jwt: $jwt) {
    id
    name
    avatarUrl
    coverUrl
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "business": {
    "name": "Mi Tienda",
    "type": "restaurant",
    "avatar": "businesses/avatars/6774abc123.jpg",
    "coverImage": "businesses/covers/6774def456.jpg",
    "description": "Descripción del negocio",
    "tags": ["comida", "rapida"]
  },
  "branches": [
    {
      "name": "Sucursal Centro",
      "coordinates": { "lat": -12.0464, "lng": -77.0428 },
      "phone": "+51999999999",
      "schedule": { "lun-vie": "9:00-18:00" },
      "address": "Av. Principal 123",
      "avatar": "branches/avatars/6774ghi789.jpg"
    }
  ]
}
```

**Response:**
```json
{
  "data": {
    "registerBusiness": {
      "id": "6774abc123def456",
      "name": "Mi Tienda",
      "avatarUrl": "https://s3.../businesses/avatars/6774abc123.jpg?...",
      "coverUrl": "https://s3.../businesses/covers/6774def456.jpg?..."
    }
  }
}
```

---

### Actualizar Negocio

```graphql
mutation UpdateBusiness($businessId: String!, $input: UpdateBusinessInput!, $jwt: String) {
  updateBusiness(businessId: $businessId, input: $input, jwt: $jwt) {
    id
    name
    avatarUrl
    coverUrl
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "businessId": "6774abc123def456",
  "input": {
    "name": "Nuevo Nombre",
    "description": "Nueva descripción",
    "avatar": "businesses/avatars/new123.jpg",
    "isActive": true
  }
}
```

---

### Crear Sucursal

```graphql
mutation CreateBranch($input: CreateBranchInput!, $jwt: String) {
  createBranch(input: $input, jwt: $jwt) {
    id
    name
    avatarUrl
    coverUrl
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "businessId": "6774abc123def456",
    "name": "Nueva Sucursal",
    "coordinates": { "lat": -12.1, "lng": -77.05 },
    "phone": "+51988888888",
    "schedule": { "lun-sab": "10:00-20:00" },
    "address": "Calle Nueva 456",
    "avatar": "branches/avatars/xyz123.jpg",
    "coverImage": "branches/covers/xyz456.jpg",
    "deliveryRadius": 5.0,
    "facilities": ["wifi", "estacionamiento"]
  }
}
```

---

### Actualizar Sucursal

```graphql
mutation UpdateBranch($branchId: String!, $input: UpdateBranchInput!, $jwt: String) {
  updateBranch(branchId: $branchId, input: $input, jwt: $jwt) {
    id
    name
    status
    avatarUrl
  }
}
```

**Variables:**
```json
{
  "jwt": "eyJhbG...",
  "branchId": "6774branch123",
  "input": {
    "name": "Sucursal Renovada",
    "phone": "+51977777777",
    "status": "active",
    "avatar": "branches/avatars/updated123.jpg"
  }
}
```

---

## Queries

### Obtener Negocios

```graphql
query GetBusinesses($jwt: String) {
  businesses(jwt: $jwt) {
    id
    name
    type
    avatarUrl
    coverUrl
    globalRating
    isActive
  }
}
```

### Obtener Negocio por ID

```graphql
query GetBusiness($id: String!, $jwt: String) {
  business(id: $id, jwt: $jwt) {
    id
    name
    type
    description
    avatarUrl
    coverUrl
    tags
  }
}
```

### Obtener Sucursales de un Negocio

```graphql
query GetBranches($businessId: String, $jwt: String) {
  branches(businessId: $businessId, jwt: $jwt) {
    id
    name
    address
    phone
    status
    avatarUrl
    coverUrl
    coordinates {
      coordinates
    }
  }
}
```

### Obtener Sucursal por ID

```graphql
query GetBranch($id: String!, $jwt: String) {
  branch(id: $id, jwt: $jwt) {
    id
    name
    address
    phone
    schedule
    facilities
    avatarUrl
    coverUrl
  }
}
```

---

## Inputs Reference

### CreateBusinessInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | Sí |
| type | String | Sí |
| avatar | String | No |
| coverImage | String | No |
| description | String | No |
| socialMedia | JSON | No |
| tags | [String] | No |

### UpdateBusinessInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| type | String | No |
| description | String | No |
| socialMedia | JSON | No |
| tags | [String] | No |
| isActive | Boolean | No |
| avatar | String | No |
| coverImage | String | No |

### CreateBranchInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| businessId | String | Sí |
| name | String | Sí |
| coordinates | CoordinatesInput | Sí |
| phone | String | Sí |
| schedule | JSON | Sí |
| address | String | No |
| managerIds | [String] | No |
| avatar | String | No |
| coverImage | String | No |
| deliveryRadius | Float | No |
| facilities | [String] | No |

### UpdateBranchInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| address | String | No |
| phone | String | No |
| schedule | JSON | No |
| status | String | No |
| deliveryRadius | Float | No |
| facilities | [String] | No |
| managerIds | [String] | No |
| avatar | String | No |
| coverImage | String | No |

### CoordinatesInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| lat | Float | Sí |
| lng | Float | Sí |
