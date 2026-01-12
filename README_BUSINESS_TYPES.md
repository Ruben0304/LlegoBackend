# Sistema de Business Types Dinámicos

Sistema completo para gestionar tipos de negocio de forma dinámica en la app iOS/Android, con soporte para modelos 3D, configuración visual y notificaciones push.

## 🚀 Instalación y Setup

### 1. Ejecutar el Seed Inicial

Poblar la base de datos con los tipos de negocio iniciales:

```bash
python seed_business_types.py
```

Esto creará 3 tipos de negocio:
- **Restaurantes** (con modelo 3D local)
- **Tiendas** (con modelo 3D local)
- **Dulcería** (con modelo 3D en S3)

### 2. Verificar el Schema GraphQL

El schema GraphQL se actualiza automáticamente. Puedes verificarlo en:

```bash
# Iniciar el servidor
python main.py

# Visitar GraphiQL (solo en desarrollo)
open http://localhost:8000/graphql

# O descargar el schema
curl http://localhost:8000/graphql/schema.graphql > schema.graphql
```

## 📱 Integración con la App

### iOS

#### 1. Registrar Device Token

Al iniciar la app, registrar el device token para recibir push notifications:

```swift
// En AppDelegate o SceneDelegate
func application(_ application: UIApplication, 
                 didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    
    // Llamar mutation GraphQL
    let mutation = RegisterDeviceTokenMutation(
        input: RegisterDeviceTokenInput(
            token: token,
            platform: .ios,
            appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
            osVersion: UIDevice.current.systemVersion
        ),
        jwt: currentUserJWT // nil si no está logueado
    )
    
    apollo.perform(mutation: mutation)
}
```

#### 2. Cargar Business Types

En el `HomeView`, cargar los tipos de negocio:

```swift
struct HomeView: View {
    @State private var businessTypes: [BusinessTypeConfig] = []
    
    var body: some View {
        ScrollView(.horizontal) {
            LazyHStack {
                ForEach(businessTypes) { type in
                    BusinessTypeCard(config: type)
                }
            }
        }
        .onAppear {
            loadBusinessTypes()
        }
    }
    
    func loadBusinessTypes() {
        let query = BusinessTypeConfigsQuery(
            lastSyncAt: UserDefaults.standard.object(forKey: "lastBusinessTypeSync") as? Date
        )
        
        apollo.fetch(query: query) { result in
            switch result {
            case .success(let data):
                self.businessTypes = data.businessTypeConfigs
                UserDefaults.standard.set(Date(), forKey: "lastBusinessTypeSync")
                
                // Descargar modelos 3D si es necesario
                downloadModelsIfNeeded(data.businessTypeConfigs)
                
            case .failure(let error):
                print("Error loading business types: \(error)")
            }
        }
    }
    
    func downloadModelsIfNeeded(_ configs: [BusinessTypeConfig]) {
        for config in configs {
            guard let urlString = config.model3dUrl,
                  let url = URL(string: urlString) else { continue }
            
            let localPath = getDocumentsDirectory()
                .appendingPathComponent(config.model3dFileName)
            
            // Verificar si necesita descarga
            if !FileManager.default.fileExists(atPath: localPath.path) ||
               needsUpdate(config) {
                downloadModel(from: url, to: localPath, version: config.model3dVersion)
            }
        }
    }
}
```

#### 3. Manejar Push Notifications

Cuando llega una notificación de nuevo tipo de negocio:

```swift
func userNotificationCenter(_ center: UNUserNotificationCenter,
                            didReceive response: UNNotificationResponse,
                            withCompletionHandler completionHandler: @escaping () -> Void) {
    let userInfo = response.notification.request.content.userInfo
    
    if let type = userInfo["type"] as? String,
       type == "NEW_BUSINESS_TYPE" {
        // Ejecutar sync incremental
        syncBusinessTypes()
    }
    
    completionHandler()
}

func syncBusinessTypes() {
    let lastSync = UserDefaults.standard.object(forKey: "lastBusinessTypeSync") as? Date
    
    let query = BusinessTypeConfigsQuery(lastSyncAt: lastSync)
    
    apollo.fetch(query: query, cachePolicy: .fetchIgnoringCacheData) { result in
        // Actualizar UI con nuevos tipos
    }
}
```

### Android

Similar al flujo de iOS, pero usando FCM para push notifications.

## 🔧 Operaciones de Admin

### Crear Nuevo Tipo de Negocio

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

**Esto automáticamente:**
1. Guarda el nuevo tipo en la base de datos
2. Obtiene todos los device tokens activos
3. Envía push notification a todos los dispositivos
4. Los usuarios reciben la notificación y sincronizan

### Actualizar Tipo Existente

```graphql
mutation UpdateRestaurante {
  updateBusinessTypeConfig(
    id: "bt_restaurante"
    jwt: "admin_jwt_token"
    input: {
      name: "Restaurantes y Cafés"
      model3dVersion: 2  # Incrementar para forzar re-descarga
    }
  ) {
    id
    name
    model3dVersion
  }
}
```

**Nota:** Las actualizaciones NO disparan push notifications. Solo la creación de nuevos tipos.

### Desactivar Tipo

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

## 📊 Estructura de Datos

### Colecciones MongoDB

#### `business_type_configs`

```json
{
  "_id": "bt_restaurante",
  "key": "RESTAURANTE",
  "name": "Restaurantes",
  "description": "Comida y Bebidas",
  "icon": "fork.knife",
  "model3dFileName": "restaurant.usdz",
  "model3dUrl": null,
  "model3dVersion": 1,
  "glowColor": "#E64D33",
  "gradient": {
    "darkColor": "#801A19",
    "mediumColor": "#B34026",
    "lightColor": "#D9734D",
    "veryLightColor": "#F2E0D9",
    "overlayColor": "#731E14"
  },
  "camera": {
    "positionX": 0.0,
    "positionY": 4.0,
    "positionZ": 0.0,
    "eulerX": -1.5708,
    "eulerY": 0.0,
    "eulerZ": 0.0
  },
  "features": [
    {
      "icon": "fork.knife",
      "title": "Gourmet",
      "subtitle": "Alta cocina",
      "sortOrder": 0
    }
  ],
  "sortOrder": 0,
  "isActive": true,
  "createdAt": "2026-01-12T10:00:00Z",
  "updatedAt": "2026-01-12T10:00:00Z"
}
```

#### `device_tokens`

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "userId": "user_123",
  "token": "abc123...xyz",
  "platform": "IOS",
  "appVersion": "1.0.0",
  "osVersion": "17.0",
  "isActive": true,
  "createdAt": "2026-01-12T10:00:00Z",
  "updatedAt": "2026-01-12T10:00:00Z"
}
```

## 🔔 Push Notifications

### Estado Actual

El servicio de push notifications está implementado como **placeholder** para desarrollo. Las notificaciones se loguean pero no se envían realmente.

### Para Producción

Necesitas configurar:

#### APNs (iOS)

1. Obtener `.p8` auth key de Apple Developer Console
2. Agregar a `.env`:
   ```
   APNS_KEY_ID=ABC123XYZ
   APNS_TEAM_ID=DEF456UVW
   APNS_KEY_PATH=/path/to/AuthKey_ABC123XYZ.p8
   APNS_TOPIC=com.llego.app
   APNS_USE_SANDBOX=false
   ```

3. Implementar en `services/push_notification_service.py`:
   ```python
   # Usar aioapns o similar
   from aioapns import APNs, NotificationRequest
   
   async def _send_apns_single(self, token, title, body, data):
       request = NotificationRequest(
           device_token=token,
           message={
               "aps": {
                   "alert": {"title": title, "body": body},
                   "sound": "default",
                   "content-available": 1
               },
               "data": data
           }
       )
       await self.apns_client.send_notification(request)
   ```

#### FCM (Android)

1. Crear proyecto en Firebase Console
2. Descargar `service-account.json`
3. Agregar a `.env`:
   ```
   FCM_CREDENTIALS_PATH=/path/to/service-account.json
   ```

4. Implementar en `services/push_notification_service.py`:
   ```python
   # Usar firebase-admin
   import firebase_admin
   from firebase_admin import messaging
   
   async def _send_fcm_single(self, token, title, body, data):
       message = messaging.Message(
           notification=messaging.Notification(title=title, body=body),
           data=data,
           token=token,
           android=messaging.AndroidConfig(priority='high')
       )
       await messaging.send_async(message)
   ```

## 📝 Archivos Creados

```
├── models_business_types.py              # Modelos Pydantic
├── repositories/
│   ├── business_type_repository.py       # Repo para business types
│   └── device_token_repository.py        # Repo para device tokens
├── services/
│   └── push_notification_service.py      # Servicio de push (placeholder)
├── schema/
│   └── business_types/
│       ├── __init__.py
│       ├── types.py                      # Tipos GraphQL
│       ├── queries.py                    # Query: businessTypeConfigs
│       └── mutations.py                  # Mutations: create, update, etc.
├── seed_business_types.py                # Script de seed
├── docs/
│   └── business-types-api.md             # Documentación completa
└── README_BUSINESS_TYPES.md              # Este archivo
```

## 🧪 Testing

### 1. Verificar Seed

```bash
python seed_business_types.py
```

### 2. Query en GraphiQL

```graphql
query TestBusinessTypes {
  businessTypeConfigs {
    id
    key
    name
    sortOrder
  }
}
```

### 3. Registrar Device Token

```graphql
mutation TestRegisterToken {
  registerDeviceToken(
    input: {
      token: "test_token_123"
      platform: IOS
      appVersion: "1.0.0"
      osVersion: "17.0"
    }
  ) {
    id
    token
    platform
  }
}
```

### 4. Crear Tipo (Admin)

```graphql
mutation TestCreateType {
  createBusinessTypeConfig(
    jwt: "your_admin_jwt"
    input: {
      key: "TEST"
      name: "Test Type"
      description: "Testing"
      icon: "star.fill"
      model3dFileName: "test.usdz"
      glowColor: "#FF0000"
      gradient: {
        darkColor: "#000000"
        mediumColor: "#333333"
        lightColor: "#666666"
        veryLightColor: "#999999"
        overlayColor: "#111111"
      }
      camera: {
        positionX: 0
        positionY: 0
        positionZ: 3
      }
      features: []
      sortOrder: 99
    }
  ) {
    id
    key
    name
  }
}
```

## 📚 Documentación Adicional

Ver `docs/business-types-api.md` para:
- Ejemplos completos de todas las operaciones
- Estructura de payloads de push
- Flujo detallado de sincronización
- Notas de implementación para iOS/Android

## ✅ Checklist de Implementación

- [x] Modelos Pydantic
- [x] Repositorios MongoDB
- [x] Servicio de Push (placeholder)
- [x] Tipos GraphQL
- [x] Queries GraphQL
- [x] Mutations GraphQL
- [x] Integración con schema principal
- [x] Script de seed
- [x] Documentación completa
- [ ] Configurar APNs para producción
- [ ] Configurar FCM para producción
- [ ] Tests unitarios
- [ ] Tests de integración

## 🤝 Contribuir

Para agregar nuevos tipos de negocio:

1. Usar la mutation `createBusinessTypeConfig` (dispara push automático)
2. O agregar al seed en `seed_business_types.py` y re-ejecutar

Para modificar tipos existentes:

1. Usar la mutation `updateBusinessTypeConfig` (NO dispara push)
2. Incrementar `model3dVersion` si cambió el modelo 3D

## 📞 Soporte

Para preguntas o issues, contactar al equipo de backend.
