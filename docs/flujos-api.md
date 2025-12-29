# Flujos de la API

Este documento describe los flujos principales de la aplicación y cómo interactúan usuarios, negocios, sucursales y productos.

---

## Modelo de Datos

```
Usuario (MongoDB)
├── businessIds[]     ← Lista de negocios que posee
├── branchIds[]       ← Lista de sucursales a las que tiene acceso
└── avatar

Negocio (Qdrant)
├── ownerId           ← Usuario propietario
└── branches[]        ← Sucursales del negocio

Sucursal (Qdrant)
├── businessId        ← Negocio al que pertenece
├── managerIds[]      ← Usuarios que pueden gestionar
└── products[]        ← Productos de la sucursal

Producto (Qdrant)
└── branchId          ← Sucursal a la que pertenece
```

---

## Flujo 1: Registro de Usuario y Negocio

### Paso 1: Registrar Usuario
```graphql
mutation {
  register(input: {
    name: "Juan Pérez"
    email: "juan@ejemplo.com"
    password: "secreto123"
    role: "merchant"
  }) {
    access_token
    user { id name businessIds branchIds }
  }
}
```

**Resultado:**
- Usuario creado con `businessIds: []` y `branchIds: []`
- Se obtiene JWT para autenticación

---

### Paso 2: Subir Imágenes (Opcional)
```bash
# Avatar del negocio
curl -X POST "/upload/business/avatar" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@logo.png"

# Cover del negocio
curl -X POST "/upload/business/cover" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@cover.jpg"
```

---

### Paso 3: Registrar Negocio con Sucursales
```graphql
mutation {
  registerBusiness(
    businessInput: {
      name: "Mi Restaurante"
      type: "restaurant"
      avatar: "businesses/avatars/xxx.jpg"
      description: "El mejor restaurante"
    }
    branchesInput: [{
      name: "Sucursal Centro"
      coordinates: { lat: -12.0464, lng: -77.0428 }
      phone: "+51999999999"
      schedule: { "lun-vie": "9:00-18:00" }
      address: "Av. Principal 123"
    }]
    jwt: "{jwt}"
  ) {
    id
    name
  }
}
```

**Lo que sucede automáticamente:**
1. Se crea el negocio con `ownerId = usuario_actual`
2. Se crea(n) la(s) sucursal(es) con `businessId = negocio_creado`
3. **El `businessId` se agrega a `businessIds` del usuario**

**Estado del usuario después:**
```json
{
  "businessIds": ["negocio_abc123"],
  "branchIds": []
}
```

---

## Flujo 2: Agregar Acceso a Sucursales

El usuario propietario del negocio puede agregar sucursales a su lista de acceso directo.

### Requisito
El usuario debe tener el `businessId` del negocio padre en su lista `businessIds`.

### Mutation
```graphql
mutation {
  addBranchToUser(
    input: { branchId: "branch_xyz789" }
    jwt: "{jwt}"
  ) {
    id
    branchIds
  }
}
```

**Validaciones:**
1. ✅ Usuario autenticado
2. ✅ Sucursal existe
3. ✅ El `businessId` de la sucursal está en `businessIds` del usuario
4. ✅ La sucursal no está ya en `branchIds`

**Estado del usuario después:**
```json
{
  "businessIds": ["negocio_abc123"],
  "branchIds": ["branch_xyz789"]
}
```

---

## Flujo 3: Crear Productos

### Opción A: Con branchId específico
```graphql
mutation {
  createProduct(
    input: {
      branchId: "branch_xyz789"
      name: "Hamburguesa Clásica"
      description: "Deliciosa hamburguesa"
      price: 15.99
      image: "products/xxx.png"
    }
    jwt: "{jwt}"
  ) {
    id
    name
  }
}
```

**Validación de permisos:**
- Usuario es `ownerId` del negocio, O
- Usuario está en `managerIds` de la sucursal

---

### Opción B: Con businessId (sin sucursal específica)
```graphql
mutation {
  createProduct(
    input: {
      businessId: "negocio_abc123"
      name: "Hamburguesa Clásica"
      description: "Deliciosa hamburguesa"
      price: 15.99
      image: "products/xxx.png"
    }
    jwt: "{jwt}"
  ) {
    id
    name
  }
}
```

**Lo que sucede:**
1. Se busca el negocio
2. Se obtienen las sucursales del negocio
3. **El producto se asigna a la primera sucursal**
4. Solo el `ownerId` del negocio puede usar esta opción

---

## Flujo 4: Gestión de Usuarios como Managers

### El propietario puede agregar managers a sucursales
```graphql
mutation {
  updateBranch(
    branchId: "branch_xyz789"
    input: {
      managerIds: ["user_manager1", "user_manager2"]
    }
    jwt: "{jwt}"
  ) {
    id
    managerIds
  }
}
```

**Nota:** Solo el `ownerId` del negocio puede modificar `managerIds`.

---

## Flujo 5: Actualizar Perfil de Usuario

### Subir Avatar
```bash
curl -X POST "/upload/user/avatar" \
  -H "Authorization: Bearer {jwt}" \
  -F "image=@foto.jpg"
```

### Actualizar Perfil
```graphql
mutation {
  updateUser(
    input: {
      name: "Juan Carlos Pérez"
      phone: "+51988888888"
      avatar: "users/avatars/xxx.jpg"
    }
    jwt: "{jwt}"
  ) {
    id
    name
    avatarUrl
  }
}
```

---

## Diagrama de Permisos

```
┌─────────────────────────────────────────────────────────────┐
│                         USUARIO                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   businessIds: ["biz1", "biz2"]                             │
│   branchIds: ["br1", "br3"]                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ¿QUÉ PUEDE HACER?                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Crear/Editar negocios donde es ownerId                  │
│  ✅ Crear sucursales en negocios donde es ownerId           │
│  ✅ Editar sucursales donde es ownerId o está en managerIds │
│  ✅ Crear productos en sucursales donde tiene permiso       │
│  ✅ Agregar a branchIds sucursales de sus negocios          │
│                                                              │
│  ❌ NO puede editar negocios de otros                       │
│  ❌ NO puede crear sucursales en negocios de otros          │
│  ❌ NO puede agregar branches de negocios que no posee      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Flujo Completo: De Registro a Venta

```
1. REGISTRO
   └── Usuario se registra → businessIds: [], branchIds: []

2. CREAR NEGOCIO
   └── registerBusiness → businessIds: ["biz1"], branchIds: []
       └── Se crean sucursales automáticamente

3. AGREGAR ACCESO A SUCURSALES (Opcional)
   └── addBranchToUser → branchIds: ["br1", "br2"]

4. SUBIR IMÁGENES DE PRODUCTOS
   └── POST /upload/product/image → image_path

5. CREAR PRODUCTOS
   └── createProduct (con branchId o businessId)

6. CONSULTAR PRODUCTOS
   └── products(branchId: "br1") → Lista de productos
```

---

## Resumen de Endpoints

### REST (Uploads)
| Endpoint | Descripción |
|----------|-------------|
| `POST /upload/user/avatar` | Avatar de usuario |
| `POST /upload/business/avatar` | Avatar de negocio |
| `POST /upload/business/cover` | Cover de negocio |
| `POST /upload/branch/avatar` | Avatar de sucursal |
| `POST /upload/branch/cover` | Cover de sucursal |
| `POST /upload/product/image` | Imagen de producto |

### GraphQL Mutations
| Mutation | Descripción |
|----------|-------------|
| `register` | Registrar usuario |
| `login` | Iniciar sesión |
| `updateUser` | Actualizar perfil |
| `addBranchToUser` | Agregar sucursal a usuario |
| `removeBranchFromUser` | Remover sucursal de usuario |
| `deleteUser` | Eliminar cuenta |
| `registerBusiness` | Crear negocio + sucursales |
| `updateBusiness` | Actualizar negocio |
| `createBranch` | Crear sucursal |
| `updateBranch` | Actualizar sucursal |
| `createProduct` | Crear producto |
| `updateProduct` | Actualizar producto |
| `deleteProduct` | Eliminar producto |

### GraphQL Queries
| Query | Descripción |
|-------|-------------|
| `me` | Usuario actual |
| `user(id)` | Usuario por ID |
| `businesses` | Lista de negocios |
| `business(id)` | Negocio por ID |
| `branches(businessId)` | Sucursales de un negocio |
| `branch(id)` | Sucursal por ID |
| `products(branchId)` | Productos de una sucursal |
| `product(id)` | Producto por ID |
