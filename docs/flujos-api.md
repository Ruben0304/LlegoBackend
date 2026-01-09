# Flujos de la API

Guía de flujos principales para integración frontend multiplataforma.

---

## Modelo de Datos

```
Usuario (MongoDB)
├── businessIds[]     ← Negocios que posee
├── branchIds[]       ← Sucursales con acceso directo
├── location          ← Ubicación actual (GeoJSON)
└── avatar

Negocio (Qdrant)
├── ownerId           ← Usuario propietario
└── branches[]        ← Sucursales del negocio

Sucursal (Qdrant + MongoDB)
├── businessId        ← Negocio padre
├── managerIds[]      ← Usuarios gestores
├── tipos[]           ← ["restaurante", "dulceria", "tienda"]
└── products[]        ← Productos

Producto (Qdrant)
└── branchId          ← Sucursal a la que pertenece
```

---

## Flujo 1: Registro y Autenticación

### Registro con Email
```graphql
mutation Register($input: RegisterInput!) {
  register(input: $input) {
    access_token
    user { id name email role }
  }
}
```
```json
{
  "input": {
    "name": "Juan Pérez",
    "email": "juan@ejemplo.com",
    "password": "secreto123",
    "phone": "+51999999999"
  }
}
```
> El rol siempre es `customer`. Solo se cambia vía DB.

### Login con Email
```graphql
mutation Login($input: LoginInput!) {
  login(input: $input) {
    access_token
    user { id name email role }
  }
}
```

### Login con Google
```graphql
mutation LoginGoogle($input: SocialLoginInput!) {
  loginWithGoogle(input: $input) {
    access_token
    user { id name email role }
  }
}
```
```json
{
  "input": {
    "id_token": "eyJhbG...",
    "nonce": "random_nonce"
  }
}
```

### Login con Apple
```graphql
mutation LoginApple($input: AppleLoginInput!) {
  loginWithApple(input: $input) {
    access_token
    user { id name email role }
  }
}
```

---

## Flujo 2: Crear Negocio con Sucursales

### Paso 1: Subir Imágenes (Opcional)
```bash
# Avatar del negocio
curl -X POST "/upload/business/avatar" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@logo.png"
# Response: { "image_path": "businesses/avatars/xxx.jpg" }

# Cover del negocio
curl -X POST "/upload/business/cover" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@cover.jpg"
```

### Paso 2: Registrar Negocio
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
    "name": "Mi Restaurante",
    "type": "restaurant",
    "avatar": "businesses/avatars/xxx.jpg",
    "description": "El mejor restaurante"
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

**Resultado automático:**
- Negocio creado con `ownerId = usuario_actual`
- Sucursal(es) creada(s) con `businessId = negocio_creado`
- `businessId` agregado a `businessIds` del usuario

---

## Flujo 3: Gestión de Sucursales

### Crear Sucursal Adicional
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
    "businessId": "negocio_abc123",
    "name": "Nueva Sucursal",
    "coordinates": { "lat": -12.1, "lng": -77.05 },
    "phone": "+51988888888",
    "schedule": { "lun-sab": "10:00-20:00" },
    "tipos": ["RESTAURANTE", "TIENDA"]
  }
}
```

### Agregar Sucursal a Usuario
```graphql
mutation AddBranchToUser($input: AddBranchToUserInput!, $jwt: String!) {
  addBranchToUser(input: $input, jwt: $jwt) {
    id
    branchIds
  }
}
```
> Requisito: El `businessId` de la sucursal debe estar en `businessIds` del usuario.

---

## Flujo 4: Crear Productos

### Paso 1: Subir Imagen
```bash
curl -X POST "/upload/product/image" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@hamburguesa.png"
# Response: { "image_path": "products/xxx.png" }
```

### Paso 2: Crear Producto
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
```json
{
  "jwt": "eyJhbG...",
  "input": {
    "branchId": "branch_xyz789",
    "name": "Hamburguesa Clásica",
    "description": "Deliciosa hamburguesa",
    "price": 15.99,
    "image": "products/xxx.png"
  }
}
```

---

## Flujo 5: Consultas con Paginación

Las queries principales usan paginación cursor-based (Relay-style):

### Productos Cercanos
```graphql
query Products($first: Int, $after: String, $jwt: String) {
  products(first: $first, after: $after, jwt: $jwt) {
    edges {
      node {
        id
        name
        price
        imageUrl
        score
        distanceKm
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

### Sucursales Cercanas
```graphql
query NearbyBranches(
  $longitude: Float!,
  $latitude: Float!,
  $first: Int,
  $radiusKm: Float,
  $tipo: BranchTipo
) {
  nearbyBranches(
    longitude: $longitude,
    latitude: $latitude,
    first: $first,
    radiusKm: $radiusKm,
    tipo: $tipo
  ) {
    edges {
      node {
        id
        name
        distanceKm
        avatarUrl
        productos { id name price imageUrl }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

---

## Flujo 6: Actualizar Ubicación del Usuario

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
> Importante: Actualizar ubicación para que el scoring por cercanía funcione.

---

## Resumen de Endpoints

### REST (Uploads)
| Endpoint | Descripción | Output |
|----------|-------------|--------|
| `POST /upload/user/avatar` | Avatar usuario | 400x400 JPG |
| `POST /upload/business/avatar` | Avatar negocio | 400x400 JPG |
| `POST /upload/business/cover` | Cover negocio | 1200x400 JPG |
| `POST /upload/branch/avatar` | Avatar sucursal | 400x400 JPG |
| `POST /upload/branch/cover` | Cover sucursal | 1200x400 JPG |
| `POST /upload/product/image` | Imagen producto | Preserva transparencia |

### GraphQL Mutations Principales
| Mutation | Descripción |
|----------|-------------|
| `register` | Registrar usuario |
| `login` | Login email/password |
| `loginWithGoogle` | Login con Google |
| `loginWithApple` | Login con Apple |
| `updateUser` | Actualizar perfil |
| `updateLocation` | Actualizar ubicación |
| `registerBusiness` | Crear negocio + sucursales |
| `createBranch` | Crear sucursal |
| `createProduct` | Crear producto |
| `updateProduct` | Actualizar producto |
| `deleteProduct` | Eliminar producto |

### GraphQL Queries Principales
| Query | Descripción |
|-------|-------------|
| `me` | Usuario actual |
| `businesses` | Lista negocios (con filtro ownerId) |
| `branches` | Sucursales (paginado, con scoring) |
| `nearbyBranches` | Sucursales cercanas (paginado) |
| `products` | Productos (paginado, con scoring) |
| `searchProducts` | Búsqueda productos (vector search) |
| `searchBranches` | Búsqueda sucursales (vector search) |

---

## Diagrama de Permisos

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
