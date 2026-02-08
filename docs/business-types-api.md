# Business Types API - Configuración Dinámica

Sistema para gestionar dinámicamente los tipos de negocio en la app iOS/Android, incluyendo modelos 3D, configuración visual y notificaciones push.

## Contexto

La app iOS tiene un `HomeView` con un carrusel de tipos de negocio. Anteriormente hardcodeado, ahora es completamente dinámico vía GraphQL.

### Elementos Configurables

- Modelo 3D (.usdz para iOS)
- Degradado de colores del fondo
- Glow color del modelo
- Configuración de cámara SceneKit
- Features/Subcategorías del panel derecho

## Flujo Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CREAR NUEVO TIPO DE NEGOCIO                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Admin ejecuta mutation createBusinessTypeConfig                         │
│                                                                              │
│  2. Backend:                                                                 │
│     - Guarda en DB                                                          │
│     - Obtiene todos los device tokens registrados                           │
│     - Envía push notification a todos via APNs/FCM                          │
│                                                                              │
│  3. App iOS recibe push:                                                    │
│     - Foreground: Muestra banner + sync automático                          │
│     - Background: Usuario toca → abre app → sync                            │
│                                                                              │
│  4. App ejecuta query businessTypeConfigs(lastSyncAt: ...)                  │
│     - Descarga configuración del nuevo tipo                                 │
│     - Si tiene model3dUrl → descarga .usdz a Documents/                     │
│     - Actualiza cache local                                                 │
│     - Refresca UI del carrusel                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Schema GraphQL

### Tipos

```graphql
type BusinessTypeConfigType {
  id: String!
  key: String!                      # "RESTAURANTE", "TIENDA", "DULCERIA", "FARMACIA"
  name: String!                     # "Restaurantes"
  description: String!              # "Comida y Bebidas"
  icon: String!                     # SF Symbol: "fork.knife"
  
  # Modelo 3D
  model3dFileName: String!          # "restaurant.usdz"
  model3dUrl: String                # URL S3 presignada (null = bundle local)
  model3dVersion: Int!              # Incrementar para forzar re-descarga
  
  # Visual
  gradient: GradientConfigType!     # Colores del fondo
  glowColor: String!                # Hex del glow del modelo 3D
  
  # Cámara SceneKit
  camera: CameraConfigType!
  
  # Subcategorías panel derecho
  features: [FeatureType!]!
  
  sortOrder: Int!                   # Orden en carrusel
  isActive: Boolean!
  createdAt: DateTime!
  updatedAt: DateTime!
}

type GradientConfigType {
  darkColor: String!
  mediumColor: String!
  lightColor: String!
  veryLightColor: String!
  overlayColor: String!
}

type CameraConfigType {
  positionX: Float!
  positionY: Float!
  positionZ: Float!
  eulerX: Float
  eulerY: Float
  eulerZ: Float
}

type FeatureType {
  icon: String!
  title: String!
  subtitle: String!
  sortOrder: Int!
}

type DeviceTokenType {
  id: String!
  userId: String                    # Null si no está logueado
  token: String!
  platform: DevicePlatform!
  appVersion: String
  osVersion: String
  isActive: Boolean!
  createdAt: DateTime!
  updatedAt: DateTime!
}

enum DevicePlatform {
  IOS
  ANDROID
}
```

### Queries

```graphql
type Query {
  # Obtener tipos de negocio activos
  # lastSyncAt: solo retorna modificados después de esta fecha (sync incremental)
  businessTypeConfigs(lastSyncAt: DateTime = null): [BusinessTypeConfigType!]!
}
```

### Mutations

```graphql
type Mutation {
  # ══════════════════════════════════════════════════════════════════════════
  # DEVICE TOKENS
  # ══════════════════════════════════════════════════════════════════════════
  
  # Registrar token para push (llamar al iniciar app)
  registerDeviceToken(input: RegisterDeviceTokenInput!, jwt: String = null): DeviceTokenType!
  
  # Desregistrar token (llamar al logout o desinstalar)
  unregisterDeviceToken(token: String!): Boolean!
  
  # ══════════════════════════════════════════════════════════════════════════
  # ADMIN: GESTIÓN DE TIPOS DE NEGOCIO
  # ══════════════════════════════════════════════════════════════════════════
  
  # Crear nuevo tipo (DISPARA PUSH A TODOS)
  createBusinessTypeConfig(input: CreateBusinessTypeConfigInput!, jwt: String!): BusinessTypeConfigType!
  
  # Actualizar tipo existente (NO dispara push)
  updateBusinessTypeConfig(id: String!, input: UpdateBusinessTypeConfigInput!, jwt: String!): BusinessTypeConfigType!
  
  # Desactivar tipo (soft delete)
  deactivateBusinessTypeConfig(id: String!, jwt: String!): BusinessTypeConfigType!
}
```

### Inputs

```graphql
input RegisterDeviceTokenInput {
  token: String!
  platform: DevicePlatform!
  appVersion: String
  osVersion: String
}

input CreateBusinessTypeConfigInput {
  key: String!
  name: String!
  description: String!
  icon: String!
  model3dFileName: String!
  model3dUrl: String
  gradient: GradientConfigInput!
  camera: CameraConfigInput!
  glowColor: String!
  features: [FeatureInput!]!
  sortOrder: Int!
  # Push notification personalizado
  pushTitle: String                 # Default: "¡Nueva categoría disponible!"
  pushBody: String                  # Default: "Descubre {name} en Llego"
}

input UpdateBusinessTypeConfigInput {
  name: String
  description: String
  icon: String
  model3dFileName: String
  model3dUrl: String
  model3dVersion: Int
  gradient: GradientConfigInput
  camera: CameraConfigInput
  glowColor: String
  features: [FeatureInput!]
  sortOrder: Int
  isActive: Boolean
}

input GradientConfigInput {
  darkColor: String!
  mediumColor: String!
  lightColor: String!
  veryLightColor: String!
  overlayColor: String!
}

input CameraConfigInput {
  positionX: Float!
  positionY: Float!
  positionZ: Float!
  eulerX: Float
  eulerY: Float
  eulerZ: Float
}

input FeatureInput {
  icon: String!
  title: String!
  subtitle: String!
  sortOrder: Int!
}
```

## Ejemplos de Uso

### 1. Registrar Device Token (iOS App Startup)

```graphql
mutation RegisterDevice {
  registerDeviceToken(
    input: {
      token: "abc123...xyz"
      platform: IOS
      appVersion: "1.0.0"
      osVersion: "17.0"
    }
    jwt: "eyJhbGc..." # Optional, si el usuario está logueado
  ) {
    id
    token
    platform
    isActive
  }
}
```

### 2. Obtener Tipos de Negocio (Primera Carga)

```graphql
query GetBusinessTypes {
  businessTypeConfigs {
    id
    key
    name
    description
    icon
    model3dFileName
    model3dUrl
    model3dVersion
    gradient {
      darkColor
      mediumColor
      lightColor
      veryLightColor
      overlayColor
    }
    camera {
      positionX
      positionY
      positionZ
      eulerX
      eulerY
      eulerZ
    }
    glowColor
    features {
      icon
      title
      subtitle
      sortOrder
    }
    sortOrder
  }
}
```

### 3. Sync Incremental (Después de Push)

```graphql
query SyncBusinessTypes {
  businessTypeConfigs(lastSyncAt: "2026-01-10T10:00:00Z") {
    id
    key
    name
    # ... resto de campos
  }
}
```

### 4. Crear Nuevo Tipo de Negocio (Admin)

```graphql
mutation CreateFarmacia {
  createBusinessTypeConfig(
    jwt: "admin_jwt_token"
    input: {
      key: "FARMACIA"
      name: "Farmacias"
      description: "Medicamentos y Salud"
      icon: "cross.case.fill"
      model3dFileName: "farmacia.usdz"
      model3dUrl: "https://s3.amazonaws.com/bucket/models/farmacia.usdz"
      glowColor: "#4CAF50"
      gradient: {
        darkColor: "#1B5E20"
        mediumColor: "#388E3C"
        lightColor: "#66BB6A"
        veryLightColor: "#E8F5E9"
        overlayColor: "#2E7D32"
      }
      camera: {
        positionX: 0
        positionY: 0
        positionZ: 3.5
      }
      features: [
        {
          icon: "pills.fill"
          title: "Medicamentos"
          subtitle: "Receta médica"
          sortOrder: 0
        }
        {
          icon: "heart.fill"
          title: "Cuidado Personal"
          subtitle: "Higiene y belleza"
          sortOrder: 1
        }
      ]
      sortOrder: 3
      pushTitle: "¡Nueva categoría disponible!"
      pushBody: "Descubre Farmacias en Llego 💊"
    }
  ) {
    id
    key
    name
  }
}
```

### 5. Actualizar Tipo Existente (Admin)

```graphql
mutation UpdateRestaurante {
  updateBusinessTypeConfig(
    id: "bt_restaurante"
    jwt: "admin_jwt_token"
    input: {
      name: "Restaurantes y Cafés"
      model3dVersion: 2  # Forzar re-descarga del modelo
    }
  ) {
    id
    name
    model3dVersion
  }
}
```

### 6. Desactivar Tipo (Admin)

```graphql
mutation DeactivateDulceria {
  deactivateBusinessTypeConfig(
    id: "bt_dulceria"
    jwt: "admin_jwt_token"
  ) {
    id
    isActive
  }
}
```

## Push Notification Payload

### APNs (iOS)

```json
{
  "aps": {
    "alert": {
      "title": "¡Nueva categoría disponible!",
      "body": "Descubre Farmacias en Llego 💊"
    },
    "sound": "default",
    "badge": 1,
    "content-available": 1
  },
  "data": {
    "type": "NEW_BUSINESS_TYPE",
    "businessTypeKey": "FARMACIA",
    "businessTypeId": "bt_farmacia",
    "action": "SYNC_BUSINESS_TYPES"
  }
}
```

### FCM (Android)

```json
{
  "message": {
    "token": "device_token",
    "notification": {
      "title": "¡Nueva categoría disponible!",
      "body": "Descubre Farmacias en Llego 💊"
    },
    "data": {
      "type": "NEW_BUSINESS_TYPE",
      "businessTypeKey": "FARMACIA",
      "businessTypeId": "bt_farmacia",
      "action": "SYNC_BUSINESS_TYPES"
    },
    "android": {
      "priority": "high"
    }
  }
}
```

## Resumen de Operaciones

| Operación | Tipo | Propósito | Dispara Push |
|-----------|------|-----------|--------------|
| `businessTypeConfigs(lastSyncAt)` | Query | Sync tipos de negocio | No |
| `registerDeviceToken(input)` | Mutation | Registrar para push | No |
| `unregisterDeviceToken(token)` | Mutation | Desregistrar al logout | No |
| `createBusinessTypeConfig(input)` | Mutation | Crear nuevo tipo | **SÍ** |
| `updateBusinessTypeConfig(id, input)` | Mutation | Actualizar existente | No |
| `deactivateBusinessTypeConfig(id)` | Mutation | Soft delete | No |

## Seeding Inicial

Para poblar la base de datos con los tipos iniciales:

```bash
python scripts/seed_business_types.py
```

Esto creará:
- Restaurantes
- Tiendas
- Dulcería

## Notas de Implementación

### Backend

1. **Push Notifications**: El servicio actual es un placeholder. Para producción, implementar:
   - APNs con autenticación JWT (.p8 key)
   - FCM con Firebase Admin SDK
   - Manejo de tokens inválidos/expirados

2. **Modelos 3D**: 
   - Si `model3dUrl` es `null`, la app usa el modelo del bundle
   - Si tiene URL, la app descarga y cachea localmente
   - Incrementar `model3dVersion` fuerza re-descarga

3. **Sync Incremental**:
   - La app guarda `lastSyncAt` localmente
   - En cada sync, pasa este timestamp
   - Backend solo retorna configs modificados después

### iOS App

1. **Registro de Token**:
   ```swift
   func application(_ application: UIApplication, 
                    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
       let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
       // Llamar mutation registerDeviceToken
   }
   ```

2. **Manejo de Push**:
   ```swift
   func userNotificationCenter(_ center: UNUserNotificationCenter,
                               didReceive response: UNNotificationResponse) {
       let userInfo = response.notification.request.content.userInfo
       if userInfo["type"] == "NEW_BUSINESS_TYPE" {
           // Ejecutar sync incremental
           syncBusinessTypes()
       }
   }
   ```

3. **Descarga de Modelos**:
   ```swift
   if let url = config.model3dUrl {
       downloadModel(from: url, version: config.model3dVersion)
   }
   ```

## TODO: Configuración de Push

Para habilitar notificaciones push en producción:

1. **APNs (iOS)**:
   - Obtener .p8 auth key de Apple Developer
   - Configurar en variables de entorno
   - Implementar `_send_apns_single()` en `push_notification_service.py`

2. **FCM (Android)**:
   - Crear proyecto en Firebase Console
   - Descargar service account credentials
   - Configurar en variables de entorno
   - Implementar `_send_fcm_single()` en `push_notification_service.py`
