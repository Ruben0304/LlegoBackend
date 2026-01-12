# Flujo de Registro de Negocio

## Autenticación
- REST: Header `Authorization: Bearer {jwt}`
- GraphQL: Parámetro `jwt: String` en cada mutation/query

---

## Negocio (Business)

### CreateBusinessInput
| Campo | Tipo | Requerido |
|-------|------|-----------|
| `name` | String | ✅ |
| `avatar` | String | ❌ |
| `coverImage` | String | ❌ |
| `description` | String | ❌ |
| `socialMedia` | JSON | ❌ |
| `tags` | [String] | ❌ |

### UpdateBusinessInput
| Campo | Tipo |
|-------|------|
| `name` | String |
| `description` | String |
| `socialMedia` | JSON |
| `tags` | [String] |
| `isActive` | Boolean |
| `avatar` | String |
| `coverImage` | String |

### Campos Automáticos
| Campo | Valor |
|-------|-------|
| `id` | ObjectId generado |
| `ownerId` | ID del usuario autenticado |
| `globalRating` | `0.0` |
| `isActive` | `true` |
| `createdAt` | Timestamp |

### Formato socialMedia
```json
{
  "facebook": "https://facebook.com/minegocio",
  "instagram": "@minegocio",
  "twitter": "@minegocio"
}
```

### Tags Sugeridos
```
comida rapida, comida criolla, vegetariano, vegano, mariscos, postres,
delivery, para llevar, reservaciones, wifi gratis, estacionamiento,
familiar, casual, terraza, pet friendly, economico, premium
```

---

## Sucursal (Branch)

### RegisterBranchInput (para registerBusiness)
| Campo | Tipo | Requerido |
|-------|------|-----------|
| `name` | String | ✅ |
| `coordinates` | CoordinatesInput | ✅ |
| `phone` | String | ✅ |
| `schedule` | JSON | ✅ |
| `tipos` | [BranchTipo] | ✅ |
| `address` | String | ❌ |
| `managerIds` | [String] | ❌ |
| `avatar` | String | ❌ |
| `coverImage` | String | ❌ |
| `deliveryRadius` | Float | ❌ |
| `facilities` | [String] | ❌ |

### CreateBranchInput (para createBranch)
| Campo | Tipo | Requerido |
|-------|------|-----------|
| `businessId` | String | ✅ |
| `name` | String | ✅ |
| `coordinates` | CoordinatesInput | ✅ |
| `phone` | String | ✅ |
| `schedule` | JSON | ✅ |
| `tipos` | [BranchTipo] | ✅ |
| `address` | String | ❌ |
| `managerIds` | [String] | ❌ |
| `avatar` | String | ❌ |
| `coverImage` | String | ❌ |
| `deliveryRadius` | Float | ❌ |
| `facilities` | [String] | ❌ |

### UpdateBranchInput
| Campo | Tipo |
|-------|------|
| `name` | String |
| `address` | String |
| `coordinates` | CoordinatesInput |
| `phone` | String |
| `schedule` | JSON |
| `status` | String |
| `deliveryRadius` | Float |
| `facilities` | [String] |
| `managerIds` | [String] |
| `avatar` | String |
| `coverImage` | String |
| `tipos` | [BranchTipo] |

### CoordinatesInput
```json
{ "lat": -12.0464, "lng": -77.0428 }
```

### Campos Automáticos
| Campo | Valor |
|-------|-------|
| `id` | ObjectId generado |
| `businessId` | ID del negocio padre |
| `status` | `"active"` |
| `managerIds` | `[ownerId]` si no se especifica |
| `createdAt` | Timestamp |

### BranchTipo (Enum)
```
RESTAURANTE, DULCERIA, TIENDA
```

### Formato Schedule
```json
{
  "mon": ["08:00-12:00", "14:00-20:00"],
  "tue": ["08:00-20:00"],
  "wed": [],
  "thu": ["08:00-20:00"],
  "fri": ["08:00-22:00"],
  "sat": ["09:00-22:00"],
  "sun": []
}
```
- Claves: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`
- Lista vacía = cerrado
- Múltiples rangos = horario partido

### Facilities Disponibles
```
wifi, estacionamiento, aire_acondicionado, terraza, area_infantil,
acceso_discapacitados, delivery, para_llevar, reservaciones, eventos,
catering, efectivo, tarjeta, transferencia, qr, pet_friendly, musica_vivo
```

---

## Imágenes (REST)

| Endpoint | Output |
|----------|--------|
| `POST /upload/business/avatar` | 400x400 JPG |
| `POST /upload/business/cover` | 1200x400 JPG |
| `POST /upload/branch/avatar` | 400x400 JPG |
| `POST /upload/branch/cover` | 1200x400 JPG |

- Max: 10MB
- Formatos: JPEG, PNG, WebP, GIF
- Body: `multipart/form-data`, campo `image`

**Response:**
```json
{
  "image_path": "businesses/avatars/xxx.jpg",
  "image_url": "https://s3.../xxx.jpg?..."
}
```
> Usar `image_path` en campos `avatar`/`coverImage`

---

## Mutations

### registerBusiness
Crea negocio con sucursal(es). Mínimo 1 sucursal requerida.

**Input:**
```graphql
registerBusiness(
  businessInput: CreateBusinessInput!,
  branchesInput: [RegisterBranchInput!]!,
  jwt: String
): BusinessType
```

**Response:**
```json
{
  "id": "6774abc123",
  "name": "Mi Café",
  "ownerId": "user123",
  "globalRating": 0.0,
  "avatar": "businesses/avatars/xxx.jpg",
  "coverImage": null,
  "description": "...",
  "socialMedia": {...},
  "tags": ["cafe"],
  "isActive": true,
  "createdAt": "2024-01-15T10:30:00Z",
  "avatarUrl": "https://s3.../presigned...",
  "coverUrl": null
}
```

### updateBusiness
```graphql
updateBusiness(
  businessId: String!,
  input: UpdateBusinessInput!,
  jwt: String
): BusinessType
```

### createBranch
```graphql
createBranch(
  input: CreateBranchInput!,
  jwt: String
): BranchType
```

### updateBranch
```graphql
updateBranch(
  branchId: String!,
  input: UpdateBranchInput!,
  jwt: String
): BranchType
```

### ⚠️ Delete
No existen mutations de eliminación. Para "eliminar":
- Negocio: usar `updateBusiness` con `isActive: false`
- Sucursal: usar `updateBranch` con `status: "inactive"`

---

## Queries

| Query | Parámetros |
|-------|------------|
| `businesses` | `ownerId?: String` |
| `business` | `id: String!` |
| `branches` | `businessId?: String, tipo?: BranchTipo, first?: Int, after?: String` |
| `branch` | `id: String!` |
| `nearbyBranches` | `longitude: Float!, latitude: Float!, radiusKm?: Float, tipo?: BranchTipo` |
| `searchBranches` | `query: String!, first?: Int` |

---

## Reglas de Negocio

1. No se puede crear negocio sin al menos 1 sucursal
2. Cada sucursal debe tener al menos 1 tipo (`tipos`)
3. El usuario autenticado se convierte en `ownerId`
4. Solo `ownerId` puede modificar `managerIds`
5. Al actualizar imagen, la anterior se elimina de S3
6. El `businessId` se agrega automáticamente a `businessIds` del usuario
