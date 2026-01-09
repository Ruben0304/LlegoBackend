# API de Negocios y Sucursales

Documentación para integración frontend multiplataforma.

---

## Tipos GraphQL

### BusinessType
```typescript
interface Business {
  id: string;
  name: string;
  type: string;              // "coffee", "restaurant", etc.
  ownerId: string;           // ID del usuario propietario
  globalRating: float;       // Rating promedio (0-5)
  avatar: string;            // Path en S3
  coverImage?: string;       // Path en S3
  description?: string;
  socialMedia?: {            // Redes sociales
    facebook?: string;
    instagram?: string;
    twitter?: string;
  };
  tags: string[];            // Tags para búsqueda
  isActive: boolean;         // Default: true
  createdAt: DateTime;
  
  // Campos computados (resolvers)
  avatarUrl?: string;        // Presigned URL
  coverUrl?: string;         // Presigned URL
}
```

### BranchType
```typescript
interface Branch {
  id: string;
  businessId: string;        // ID del negocio padre
  name: string;
  address?: string;
  coordinates: {             // GeoJSON Point
    type: "Point";
    coordinates: [lng, lat]; // [longitude, latitude]
  };
  phone: string;
  schedule: {                // Horario por día
    mon?: string[];          // ["08:00-12:00", "14:00-20:00"]
    tue?: string[];
    // ...
  };
  managerIds: string[];      // IDs de usuarios gestores
  status: string;            // "active" | "inactive"
  avatar?: string;           // Path en S3
  coverImage?: string;       // Path en S3
  deliveryRadius?: float;    // Radio de delivery en km
  facilities: string[];      // ["wifi", "estacionamiento", ...]
  tipos: BranchTipo[];       // ["restaurante", "dulceria", "tienda"]
  createdAt: DateTime;
  
  // Campos computados (resolvers)
  avatarUrl?: string;        // Presigned URL
  coverUrl?: string;         // Presigned URL
  products: Product[];       // Productos (con limit y availableOnly)
}

enum BranchTipo {
  RESTAURANTE = "restaurante"
  DULCERIA = "dulceria"
  TIENDA = "tienda"
}
```

### ScoredBranchType (para queries paginadas)
```typescript
interface ScoredBranch extends Branch {
  score: float;              // Score de relevancia (0-1)
  distanceM?: float;         // Distancia en metros
  distanceKm?: float;        // Distancia en km (computed)
}
```

### NearbyBranchType (para nearbyBranches)
```typescript
interface NearbyBranch extends Branch {
  distanceM: float;          // Distancia en metros
  distanceKm: float;         // Distancia en km (computed)
}
```

---

## Endpoints REST - Upload de Imágenes

### Avatar de Negocio
```bash
POST /upload/business/avatar
Authorization: Bearer {jwt}
Content-Type: multipart/form-data

# Form: image=@logo.png
# Output: 400x400 JPG
```

### Cover de Negocio
```bash
POST /upload/business/cover
Authorization: Bearer {jwt}

# Output: 1200x400 JPG
```

### Avatar de Sucursal
```bash
POST /upload/branch/avatar
Authorization: Bearer {jwt}

# Output: 400x400 JPG
```

### Cover de Sucursal
```bash
POST /upload/branch/cover
Authorization: Bearer {jwt}

# Output: 1200x400 JPG
```

**Response (todos):**
```json
{
  "image_path": "businesses/avatars/6774abc123.jpg",
  "image_url": "https://s3.../businesses/avatars/6774abc123.jpg?..."
}
```

---

## Mutations

### Registrar Negocio con Sucursales
```graphql
mutation RegisterBusiness(
  $business: CreateBusinessInput!,
  $branches: [RegisterBranchInput!]!,
  $jwt: String
) {
  registerBusiness(businessInput: $business, branchesInput: $branches, jwt: $jwt) {
    id
    name
    avatarUrl
    coverUrl
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "business": {
    "name": "Mi Tienda",
    "type": "restaurant",
    "avatar": "businesses/avatars/xxx.jpg",
    "coverImage": "businesses/covers/xxx.jpg",
    "description": "Descripción",
    "tags": ["comida", "rapida"]
  },
  "branches": [{
    "name": "Sucursal Centro",
    "coordinates": { "lat": -12.0464, "lng": -77.0428 },
    "phone": "+51999999999",
    "schedule": { "lun-vie": "9:00-18:00" },
    "tipos": ["RESTAURANTE"],
    "address": "Av. Principal 123"
  }]
}
```
> El `businessId` se agrega automáticamente a `businessIds` del usuario.

### Actualizar Negocio
```graphql
mutation UpdateBusiness($businessId: String!, $input: UpdateBusinessInput!, $jwt: String) {
  updateBusiness(businessId: $businessId, input: $input, jwt: $jwt) {
    id
    name
    avatarUrl
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "businessId": "6774abc123",
  "input": {
    "name": "Nuevo Nombre",
    "description": "Nueva descripción",
    "isActive": true
  }
}
```

### Crear Sucursal
```graphql
mutation CreateBranch($input: CreateBranchInput!, $jwt: String) {
  createBranch(input: $input, jwt: $jwt) {
    id
    name
    avatarUrl
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "businessId": "6774abc123",
    "name": "Nueva Sucursal",
    "coordinates": { "lat": -12.1, "lng": -77.05 },
    "phone": "+51988888888",
    "schedule": { "lun-sab": "10:00-20:00" },
    "tipos": ["RESTAURANTE", "TIENDA"],
    "address": "Calle Nueva 456",
    "deliveryRadius": 5.0,
    "facilities": ["wifi", "estacionamiento"]
  }
}
```

### Actualizar Sucursal
```graphql
mutation UpdateBranch($branchId: String!, $input: UpdateBranchInput!, $jwt: String) {
  updateBranch(branchId: $branchId, input: $input, jwt: $jwt) {
    id
    name
    status
  }
}
```
```json
{
  "jwt": "eyJhbG...",
  "branchId": "6774branch123",
  "input": {
    "name": "Sucursal Renovada",
    "status": "active",
    "tipos": ["RESTAURANTE", "DULCERIA"]
  }
}
```
> Solo el `ownerId` puede modificar `managerIds`.

---

## Queries

### Lista de Negocios
```graphql
query GetBusinesses($ownerId: String, $jwt: String) {
  businesses(ownerId: $ownerId, jwt: $jwt) {
    id
    name
    type
    avatarUrl
    globalRating
    isActive
  }
}
```

### Negocio por ID
```graphql
query GetBusiness($id: String!, $jwt: String) {
  business(id: $id, jwt: $jwt) {
    id
    name
    description
    avatarUrl
    coverUrl
    tags
  }
}
```

### Buscar Negocios
```graphql
query SearchBusinesses($query: String!, $useVectorSearch: Boolean, $jwt: String) {
  searchBusinesses(query: $query, useVectorSearch: $useVectorSearch, jwt: $jwt) {
    id
    name
    avatarUrl
  }
}
```

### Sucursales (Paginado con Scoring)
```graphql
query GetBranches(
  $first: Int,
  $after: String,
  $businessId: String,
  $tipo: BranchTipo,
  $radiusKm: Float,
  $jwt: String
) {
  branches(
    first: $first,
    after: $after,
    businessId: $businessId,
    tipo: $tipo,
    radiusKm: $radiusKm,
    jwt: $jwt
  ) {
    edges {
      node {
        id
        name
        address
        phone
        status
        avatarUrl
        score
        distanceKm
        tipos
        products(limit: 6) {
          id
          name
          price
          imageUrl
        }
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
      totalCount
    }
  }
}
```
> Sin `first`: retorna todos. Con `first`: paginación cursor-based.

### Sucursal por ID
```graphql
query GetBranch($id: String!, $jwt: String) {
  branch(id: $id, jwt: $jwt) {
    id
    name
    address
    phone
    schedule
    facilities
    tipos
    avatarUrl
    coverUrl
    products { id name price imageUrl }
  }
}
```

### Sucursales Cercanas (Geoespacial)
```graphql
query NearbyBranches(
  $longitude: Float!,
  $latitude: Float!,
  $first: Int,
  $after: String,
  $radiusKm: Float,
  $onlyActive: Boolean,
  $tipo: BranchTipo,
  $jwt: String
) {
  nearbyBranches(
    longitude: $longitude,
    latitude: $latitude,
    first: $first,
    after: $after,
    radiusKm: $radiusKm,
    onlyActive: $onlyActive,
    tipo: $tipo,
    jwt: $jwt
  ) {
    edges {
      node {
        id
        name
        address
        phone
        distanceM
        distanceKm
        avatarUrl
        tipos
        products(limit: 6) { id name price imageUrl }
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
      totalCount
    }
  }
}
```
```json
{
  "longitude": -77.0428,
  "latitude": -12.0464,
  "first": 10,
  "radiusKm": 5.0,
  "onlyActive": true,
  "tipo": "RESTAURANTE"
}
```
> Resultados ordenados por cercanía.

### Buscar Sucursales
```graphql
query SearchBranches(
  $query: String!,
  $first: Int,
  $useVectorSearch: Boolean,
  $radiusKm: Float,
  $jwt: String
) {
  searchBranches(
    query: $query,
    first: $first,
    useVectorSearch: $useVectorSearch,
    radiusKm: $radiusKm,
    jwt: $jwt
  ) {
    edges {
      node { id name score distanceKm }
      cursor
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

### Ubicación de Sucursal
```graphql
query BranchLocation($branchId: String!, $jwt: String) {
  branchLocation(branchId: $branchId, jwt: $jwt) {
    type
    coordinates
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

### RegisterBranchInput (para registerBusiness)
| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | Sí |
| coordinates | CoordinatesInput | Sí |
| phone | String | Sí |
| schedule | JSON | Sí |
| tipos | [BranchTipo] | Sí |
| address | String | No |
| managerIds | [String] | No |
| avatar | String | No |
| coverImage | String | No |
| deliveryRadius | Float | No |
| facilities | [String] | No |

### CreateBranchInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| businessId | String | Sí |
| name | String | Sí |
| coordinates | CoordinatesInput | Sí |
| phone | String | Sí |
| schedule | JSON | Sí |
| tipos | [BranchTipo] | Sí |
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
| coordinates | CoordinatesInput | No |
| phone | String | No |
| schedule | JSON | No |
| status | String | No |
| deliveryRadius | Float | No |
| facilities | [String] | No |
| managerIds | [String] | No |
| avatar | String | No |
| coverImage | String | No |
| tipos | [BranchTipo] | No |

### CoordinatesInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| lat | Float | Sí |
| lng | Float | Sí |

### BranchTipo (Enum)
| Valor | Descripción |
|-------|-------------|
| RESTAURANTE | Restaurante |
| DULCERIA | Dulcería |
| TIENDA | Tienda |

---

## Notas sobre Coordenadas

- Formato GeoJSON: `[longitude, latitude]` (lng, lat)
- Input usa `{ lat, lng }` para mayor claridad
- Las ubicaciones se sincronizan en MongoDB `stores_location` con índice geoespacial
- Al cambiar `status`, se actualiza `active` en `stores_location`
