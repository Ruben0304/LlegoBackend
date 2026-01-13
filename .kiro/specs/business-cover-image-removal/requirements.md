# Documento de Requisitos

## Introducción

Esta especificación define la eliminación del atributo `coverImage` (imagen de portada) del modelo de negocio (`Business`), manteniendo únicamente el avatar opcional. Las sucursales (`Branch`) conservarán tanto avatar como imagen de portada opcionales. Adicionalmente, se implementará una lógica de herencia donde las sucursales sin avatar propio heredarán el avatar del negocio al que pertenecen.

## Glosario

- **Business**: Entidad que representa un negocio en el sistema, con un propietario y múltiples sucursales.
- **Branch**: Entidad que representa una sucursal física de un negocio.
- **Avatar**: Imagen de perfil cuadrada (400x400) que identifica visualmente a un negocio o sucursal.
- **CoverImage**: Imagen de portada rectangular (1200x400) usada como banner visual.
- **Avatar_Heredado**: Avatar de sucursal que proviene del negocio padre cuando la sucursal no tiene avatar propio.
- **Presigned_URL**: URL temporal firmada para acceder a imágenes almacenadas en S3.

## Requisitos

### Requisito 1: Eliminación de coverImage del modelo Business

**Historia de Usuario:** Como desarrollador del sistema, quiero eliminar el campo coverImage del modelo Business, para simplificar la estructura de datos y reducir complejidad innecesaria.

#### Criterios de Aceptación

1. THE Business_Model SHALL NOT contain a coverImage field
2. WHEN a Business is created, THE System SHALL NOT accept coverImage as input parameter
3. WHEN a Business is updated, THE System SHALL NOT accept coverImage as update field
4. THE BusinessType GraphQL type SHALL NOT expose coverImage or cover_url fields
5. WHEN querying a Business, THE System SHALL NOT return coverImage data

### Requisito 2: Eliminación del endpoint de upload de cover para Business

**Historia de Usuario:** Como desarrollador del sistema, quiero eliminar el endpoint de subida de imagen de portada para negocios, para mantener consistencia con el modelo simplificado.

#### Criterios de Aceptación

1. THE Upload_API SHALL NOT provide a /upload/business/cover endpoint
2. WHEN a request is made to /upload/business/cover, THE System SHALL return a 404 Not Found response

### Requisito 3: Mantenimiento de imágenes en Branch

**Historia de Usuario:** Como propietario de negocio, quiero que mis sucursales mantengan tanto avatar como imagen de portada opcionales, para personalizar la presentación visual de cada ubicación.

#### Criterios de Aceptación

1. THE Branch_Model SHALL contain both avatar and coverImage as optional fields
2. WHEN a Branch is created, THE System SHALL accept avatar and coverImage as optional input parameters
3. WHEN a Branch is updated, THE System SHALL accept avatar and coverImage as optional update fields
4. THE BranchType GraphQL type SHALL expose avatar, avatar_url, coverImage and cover_url fields

### Requisito 4: Herencia de avatar del negocio a sucursal

**Historia de Usuario:** Como propietario de negocio, quiero que mis sucursales sin avatar propio muestren automáticamente el avatar del negocio, para mantener consistencia visual de marca sin duplicar imágenes.

#### Criterios de Aceptación

1. WHEN a Branch has no avatar AND the parent Business has an avatar, THE BranchType.avatar_url resolver SHALL return the Business avatar presigned URL
2. WHEN a Branch has its own avatar, THE BranchType.avatar_url resolver SHALL return the Branch avatar presigned URL
3. WHEN a Branch has no avatar AND the parent Business has no avatar, THE BranchType.avatar_url resolver SHALL return null
4. WHEN resolving avatar_url for a Branch, THE System SHALL fetch the parent Business to check for avatar inheritance
5. THE Branch.avatar field in the database SHALL remain unchanged (null or empty) when using inherited avatar

### Requisito 5: Limpieza de datos existentes

**Historia de Usuario:** Como administrador del sistema, quiero que los datos existentes de coverImage en negocios sean manejados correctamente durante la migración, para evitar inconsistencias.

#### Criterios de Aceptación

1. WHEN the system processes existing Business records with coverImage, THE Repository SHALL ignore the coverImage field
2. THE System SHALL NOT fail when reading Business records that contain legacy coverImage data
3. WHEN updating a Business, THE System SHALL NOT modify or preserve any existing coverImage data

### Requisito 6: Consistencia en tipos GraphQL de Branch

**Historia de Usuario:** Como desarrollador frontend, quiero que todos los tipos de Branch (BranchType, NearbyBranchType, ScoredBranchType) soporten la herencia de avatar, para tener comportamiento consistente en toda la API.

#### Criterios de Aceptación

1. THE NearbyBranchType.avatar_url resolver SHALL implement avatar inheritance from parent Business
2. THE ScoredBranchType.avatar_url resolver SHALL implement avatar inheritance from parent Business
3. FOR ALL Branch GraphQL types, THE avatar_url resolver SHALL behave identically regarding inheritance logic
