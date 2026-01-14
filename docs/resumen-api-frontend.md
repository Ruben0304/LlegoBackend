# Resumen API Backend para Frontend

Documentación completa para integración: Usuario, Negocio y Sucursales.

---

## Modelo de Datos - Relaciones

```
Usuario (MongoDB)
├── businessIds[]     → Negocios que posee (automático al crear negocio)
├── branchIds[]       → Sucursales con acceso directo
├── location          → Ubicación actual (para scoring de cercanía)
└── avatar            → Foto de perfil

Negocio (Qdrant)
├── ownerId           → Usuario propietario (automático)
├── avatar            → Logo del negocio (opcional)
└── branches[]        → Sucursales del negocio

Sucursal (Qdrant + MongoDB)
├── businessId        → Negocio padre (obligatorio)
├── managerIds[]      → Usuarios gestores adicionales
├── avatar            → Foto de sucursal (hereda del negocio si no tiene)
├── coverImage        → Imagen de portada (opcional)
└── productos[]       → Productos de la sucursal
```

---

## 👤 USUARIO

### Obtener datos del usuario actual

```graphql
query Me($jwt: String!) {
  me(jwt: $jwt) {
    id
    name
    email
    phone
    role
    avatarUrl
    businessIds
    branchIds
    createdAt
  }
}
```

### Campos del Usuario

| Campo | Tipo | Editable | Cómo editar | Notas |
|-------|------|----------|-------------|-------|
| id | String | ❌ | - | Generado automáticamente |
| name | String | ✅ | `updateUser` | - |
| email | String | ❌ | - | No editable después del registro |
| phone | String | ✅ | `updateUser` | Opcional |
| role | String | ❌ | Solo vía DB | "customer" \| "merchant" \| "admin" |
| avatar | String | ✅ | Upload + `updateUser` | Path en S3 |
| avatarUrl | String | - | Computado | Presigned URL (solo lectura) |
| businessIds | [String] | ❌ | Automático | Se llena al crear negocio |
| branchIds | [String] | ✅ | `addBranchToUser` / `removeBranchFromUser` | - |
| location | Object | ✅ | `updateLocation` | GeoJSON Point |
| createdAt | DateTime | ❌ | - | Generado automáticamente |

### Actualizar perfil de usuario

**Paso 1: Subir avatar (si aplica)**
```bash
POST /upload/user/avatar
Authorization: Bearer {jwt}
Content-Type: multipart/form-data
Body: image=@foto.jpg

# Response:
{
  "image_path": "users/avatars/6774abc123_1234567890.jpg",
  "image_url": "https://s3.../users/avatars/..."
}
```

**Paso 2: Actualizar datos**
```graphql
mutation UpdateUser($input: UpdateUserInput!, $jwt: String!) {
  updateUser(input: $input, jwt: $jwt) {
    id
    name
    phone
    avatarUrl
  }
}
```

```json
{
  "jwt": "eyJhbG...",
  "input": {
    "name": "Juan Carlos Pérez",
    "phone": "+51988888888",
    "avatar": "users/avatars/6774abc123_1234567890.jpg"
  }
}
```

### UpdateUserInput

| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| phone | String | No |
| avatar | String | No |

### Actualizar ubicación

```graphql
mutation UpdateLocation($input: UpdateLocationInput!, $jwt: String) {
  updateLocation(input: $input, jwt: $jwt) {
    id
    name
  }
}
```

```json
{
  "jwt": "eyJhbG...",
  "input": {
    "longitude": -77.0428,
    "latitude": -12.0464
  }
}
```

> ⚠️ Importante: Actualizar ubicación para que el scoring por cercanía funcione correctamente.

---

## 🏢 NEGOCIO

### Obtener negocios

```graphql
# Mis negocios (filtrar por mi ID de usuario)
query GetBusinesses($ownerId: String, $jwt: String) {
  businesses(ownerId: $ownerId, jwt: $jwt) {
    id
    name
    description
    avatarUrl
    globalRating
    isActive
    tags
    socialMedia
  }
}

# Negocio específico por ID
query GetBusiness($id: String!, $jwt: String) {
  business(id: $id, jwt: $jwt) {
    id
    name
    description
    avatarUrl
    globalRating
    isActive
    tags
    socialMedia
  }
}
```

### Campos del Negocio

| Campo | Tipo | Editable | Requerido al crear | Notas |
|-------|------|----------|-------------------|-------|
| id | String | ❌ | - | Generado automáticamente |
| name | String | ✅ | ✅ Sí | - |
| ownerId | String | ❌ | - | Automático (usuario actual) |
| description | String | ✅ | ❌ No | Opcional |
| avatar | String | ✅ | ❌ No | Path en S3 |
| avatarUrl | String | - | - | Computado (Presigned URL) |
| socialMedia | JSON | ✅ | ❌ No | `{facebook, instagram, twitter}` |
| tags | [String] | ✅ | ❌ No | Para búsqueda |
| isActive | Boolean | ✅ | ❌ No | Default: true |
| globalRating | Float | ❌ | - | Calculado (0-5) |
| createdAt | DateTime | ❌ | - | Generado automáticamente |

> ⚠️ **IMPORTANTE**: El negocio **NO tiene coverImage**. Solo avatar.

### Crear negocio con sucursales

**Paso 1: Subir avatar (opcional)**
```bash
POST /upload/business/avatar
Authorization: Bearer {jwt}
Content-Type: multipart/form-data
Body: image=@logo.png

# Response:
{
  "image_path": "businesses/avatars/xxx.jpg",
  "image_url": "https://s3.../businesses/avatars/xxx.jpg?..."
}
```

**Paso 2: Registrar negocio**
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
  }
}
```

```json
{
  "jwt": "eyJhbG...",
  "business": {
    "name": "Mi Restaurante",
    "avatar": "businesses/avatars/xxx.jpg",
    "description": "El mejor restaurante de la ciudad",
    "tags": ["comida", "peruana"],
    "socialMedia": {
      "instagram": "@mirestaurante",
      "facebook": "mirestaurante"
    }
  },
  "branches": [{
    "name": "Sucursal Centro",
    "coordinates": { "lat": -12.0464, "lng": -77.0428 },
    "phone": "+51999999999",
    "schedule": { "lun-vie": "9:00-18:00", "sab": "10:00-14:00" },
    "tipos": ["RESTAURANTE"],
    "address": "Av. Principal 123"
  }]
}
```

**Resultado automático:**
- Negocio creado con `ownerId = usuario_actual`
- Sucursal(es) creada(s) con `businessId = negocio_creado`
- `businessId` agregado a `businessIds` del usuario

### CreateBusinessInput

| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | ✅ Sí |
| avatar | String | No |
| description | String | No |
| socialMedia | JSON | No |
| tags | [String] | No |

### Actualizar negocio

```graphql
mutation UpdateBusiness($businessId: String!, $input: UpdateBusinessInput!, $jwt: String) {
  updateBusiness(businessId: $businessId, input: $input, jwt: $jwt) {
    id
    name
    avatarUrl
    description
    isActive
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
    "isActive": true,
    "avatar": "businesses/avatars/nuevo.jpg"
  }
}
```

### UpdateBusinessInput

| Campo | Tipo | Requerido |
|-------|------|-----------|
| name | String | No |
| description | String | No |
| socialMedia | JSON | No |
| tags | [String] | No |
| isActive | Boolean | No |
| avatar | String | No |

---

## 🏪 SUCURSAL

### Obtener sucursales

```graphql
# Sucursales de un negocio específico
query GetBranches($businessId: String, $first: Int, $jwt: String) {
  branches(businessId: $businessId, first: $first, jwt: $jwt) {
    edges {
      node {
        id
        name
        address
        phone
        schedule
        status
        tipos
        facilities
        deliveryRadius
        avatarUrl
        coverUrl
        managerIds
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

# Sucursal específica por ID
query GetBranch($id: String!, $jwt: String) {
  branch(id: $id, jwt: $jwt) {
    id
    name
    address
    phone
    schedule
    status
    tipos
    facilities
    deliveryRadius
    avatarUrl
    coverUrl
    managerIds
    products { id name price imageUrl }
  }
}
```

### Campos de la Sucursal

| Campo | Tipo | Editable | Requerido al crear | Notas |
|-------|------|----------|-------------------|-------|
| id | String | ❌ | - | Generado automáticamente |
| businessId | String | ❌ | ✅ Sí | Solo al crear |
| name | String | ✅ | ✅ Sí | - |
| address | String | ✅ | ❌ No | Dirección textual |
| coordinates | Object | ✅ | ✅ Sí | `{lat, lng}` |
| phone | String | ✅ | ✅ Sí | - |
| schedule | JSON | ✅ | ✅ Sí | Horario por día |
| tipos | [BranchTipo] | ✅ | ✅ Sí | Ver enum abajo |
| status | String | ✅ | ❌ No | "active" \| "inactive" (default: "active") |
| avatar | String | ✅ | ❌ No | Path en S3 |
| avatarUrl | String | - | - | Computado (hereda del negocio si no tiene) |
| coverImage | String | ✅ | ❌ No | Path en S3 |
| coverUrl | String | - | - | Computado (Presigned URL) |
| deliveryRadius | Float | ✅ | ❌ No | Radio en km |
| facilities | [String] | ✅ | ❌ No | ["wifi", "estacionamiento", ...] |
| managerIds | [String] | ✅* | ❌ No | *Solo editable por owner |
| createdAt | DateTime | ❌ | - | Generado automáticamente |

### ⭐ Herencia de Avatar

Si la sucursal **no tiene avatar propio**, `avatarUrl` devuelve automáticamente el avatar del negocio padre.

```
Sucursal.avatar = null  →  avatarUrl = Business.avatarUrl
Sucursal.avatar = "x"   →  avatarUrl = Sucursal presigned URL
```

### BranchTipo (Enum)

| Valor | Descripción |
|-------|-------------|
| RESTAURANTE | Restaurante |
| DULCERIA | Dulcería |
| TIENDA | Tienda |

### Crear sucursal

**Paso 1: Subir imágenes (opcional)**
```bash
# Avatar de sucursal
POST /upload/branch/avatar
Authorization: Bearer {jwt}
Body: image=@avatar.jpg
# Output: 400x400 JPG

# Cover de sucursal
POST /upload/branch/cover
Authorization: Bearer {jwt}
Body: image=@cover.jpg
# Output: 1200x400 JPG
```

**Paso 2: Crear sucursal**
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

```json
{
  "jwt": "eyJhbG...",
  "input": {
    "businessId": "6774abc123",
    "name": "Nueva Sucursal",
    "coordinates": { "lat": -12.1, "lng": -77.05 },
    "phone": "+51988888888",
    "schedule": { 
      "lun-vie": "10:00-20:00",
      "sab": "10:00-14:00"
    },
    "tipos": ["RESTAURANTE", "TIENDA"],
    "address": "Calle Nueva 456",
    "deliveryRadius": 5.0,
    "facilities": ["wifi", "estacionamiento"],
    "avatar": "branches/avatars/xxx.jpg",
    "coverImage": "branches/covers/xxx.jpg"
  }
}
```

### CreateBranchInput

| Campo | Tipo | Requerido |
|-------|------|-----------|
| businessId | String | ✅ Sí |
| name | String | ✅ Sí |
| coordinates | CoordinatesInput | ✅ Sí |
| phone | String | ✅ Sí |
| schedule | JSON | ✅ Sí |
| tipos | [BranchTipo] | ✅ Sí |
| address | String | No |
| managerIds | [String] | No |
| avatar | String | No |
| coverImage | String | No |
| deliveryRadius | Float | No |
| facilities | [String] | No |

### Actualizar sucursal

```graphql
mutation UpdateBranch($branchId: String!, $input: UpdateBranchInput!, $jwt: String) {
  updateBranch(branchId: $branchId, input: $input, jwt: $jwt) {
    id
    name
    status
    avatarUrl
    coverUrl
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
    "tipos": ["RESTAURANTE", "DULCERIA"],
    "phone": "+51977777777"
  }
}
```

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
| managerIds | [String] | No* |
| avatar | String | No |
| coverImage | String | No |
| tipos | [BranchTipo] | No |

*`managerIds` solo editable por el owner del negocio

### Eliminar sucursal

```graphql
mutation DeleteBranch($branchId: String!, $jwt: String) {
  deleteBranch(branchId: $branchId, jwt: $jwt)
}
```

```json
{
  "jwt": "eyJhbG...",
  "branchId": "6774branch123"
}
```

**Response:** `true` si se eliminó correctamente.

**Importante:**
- Solo el **owner del negocio** puede eliminar sucursales (los managers no pueden)
- Al eliminar una sucursal se eliminan también:
  - Todos los productos de la sucursal
  - Las imágenes (avatar, cover) de S3
  - La ubicación de `stores_location`

---

## 📸 Resumen de Endpoints de Upload (REST)

| Endpoint | Entidad | Tipo | Output |
|----------|---------|------|--------|
| `POST /upload/user/avatar` | Usuario | Avatar | 400x400 JPG |
| `POST /upload/business/avatar` | Negocio | Avatar | 400x400 JPG |
| `POST /upload/branch/avatar` | Sucursal | Avatar | 400x400 JPG |
| `POST /upload/branch/cover` | Sucursal | Cover | 1200x400 JPG |
| `POST /upload/product/image` | Producto | Imagen | Preserva transparencia |

> ⚠️ **NO existe** `/upload/business/cover` - El negocio no tiene imagen de portada.

**Flujo de upload:**
1. `POST /upload/...` con `image=@archivo.jpg` → Devuelve `image_path`
2. Usar ese `image_path` en la mutation correspondiente (`updateUser`, `updateBusiness`, `updateBranch`, etc.)

---

## 🔐 Permisos

### Usuario
- Solo puede editar su propio perfil
- Solo puede eliminar su propia cuenta

### Negocio
- Solo editable por su `ownerId`
- El `businessId` se agrega automáticamente a `businessIds` del usuario al crear

### Sucursal
- Editable por:
  - Owner del negocio padre (`ownerId`)
  - Usuarios en `managerIds` de la sucursal
- `managerIds` solo modificable por el owner
- Para agregar sucursal a `branchIds` del usuario, el `businessId` debe estar en sus `businessIds`

```
┌─────────────────────────────────────────────────────────────┐
│                         USUARIO                              │
├─────────────────────────────────────────────────────────────┤
│  businessIds: ["biz1"]  →  Es dueño de estos negocios       │
│  branchIds: ["br1"]     →  Tiene acceso directo             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PERMISOS                                  │
├─────────────────────────────────────────────────────────────┤
│  ✅ Crear/Editar negocios donde es ownerId                  │
│  ✅ Crear sucursales en sus negocios                        │
│  ✅ Editar sucursales donde es owner o está en managerIds   │
│  ✅ Crear productos donde tiene permiso                     │
│  ❌ NO puede editar negocios/sucursales de otros            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo Típico: Usuario Nuevo → Crear Negocio

1. **Login/Register** → Obtener JWT
2. **(Opcional)** Upload avatar del negocio: `POST /upload/business/avatar`
3. **Registrar negocio** con `registerBusiness` (incluye al menos 1 sucursal)
4. El `businessId` se agrega automáticamente a `businessIds` del usuario
5. Para más sucursales: usar `createBranch`

---

## 📋 Queries Principales

| Query | Descripción | Paginación |
|-------|-------------|------------|
| `me` | Usuario actual | No |
| `businesses` | Lista negocios (filtro por ownerId) | No |
| `business` | Negocio por ID | No |
| `branches` | Sucursales (con scoring) | Cursor-based |
| `branch` | Sucursal por ID | No |
| `nearbyBranches` | Sucursales cercanas | Cursor-based |
| `searchBranches` | Búsqueda de sucursales | Cursor-based |

## 📝 Mutations Principales

| Mutation | Descripción |
|----------|-------------|
| `register` | Registrar usuario |
| `login` | Login email/password |
| `loginWithGoogle` | Login con Google |
| `loginWithApple` | Login con Apple |
| `updateUser` | Actualizar perfil usuario |
| `updateLocation` | Actualizar ubicación usuario |
| `registerBusiness` | Crear negocio + sucursales |
| `updateBusiness` | Actualizar negocio |
| `createBranch` | Crear sucursal |
| `updateBranch` | Actualizar sucursal |
| `deleteBranch` | Eliminar sucursal |
| `addBranchToUser` | Agregar sucursal a usuario |
| `removeBranchFromUser` | Remover sucursal de usuario |
