# API de Avatar de Usuario

## Endpoint: Actualizar Avatar de Usuario

### `PUT /users/avatar`

Actualiza la foto de avatar del usuario autenticado.

#### Autenticación
Requiere JWT token en el header `Authorization: Bearer <token>`

#### Request

**Content-Type:** `multipart/form-data`

**Parámetros:**
- `image` (file, required): Archivo de imagen del avatar
  - Formatos permitidos: JPEG, PNG, WebP, GIF
  - Tamaño máximo: 10MB
  - La imagen será procesada y redimensionada a 400x400 píxeles en formato JPG

#### Response

**Status Code:** `200 OK`

**Body:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "avatar": "users/avatars/507f1f77bcf86cd799439011.jpg",
  "avatar_url": "https://s3.amazonaws.com/bucket/users/avatars/507f1f77bcf86cd799439011.jpg?presigned=..."
}
```

**Campos:**
- `id`: ID del usuario
- `avatar`: Ruta del avatar en S3
- `avatar_url`: URL firmada para acceder al avatar (válida por tiempo limitado)

#### Errores

**401 Unauthorized**
```json
{
  "detail": "No autorizado"
}
```

**404 Not Found**
```json
{
  "detail": "Usuario no encontrado"
}
```

**413 Request Entity Too Large**
```json
{
  "detail": "Archivo muy grande. Máximo: 10MB"
}
```

**415 Unsupported Media Type**
```json
{
  "detail": "Tipo de archivo no permitido. Permitidos: JPEG, PNG, WebP, GIF"
}
```

**400 Bad Request**
```json
{
  "detail": "El archivo no es una imagen válida"
}
```

#### Ejemplo de uso

**cURL:**
```bash
curl -X PUT "http://localhost:8000/users/avatar" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -F "image=@/path/to/avatar.jpg"
```

**JavaScript (Fetch):**
```javascript
const formData = new FormData();
formData.append('image', fileInput.files[0]);

const response = await fetch('http://localhost:8000/users/avatar', {
  method: 'PUT',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const data = await response.json();
console.log('Avatar actualizado:', data.avatar_url);
```

**Python (requests):**
```python
import requests

url = "http://localhost:8000/users/avatar"
headers = {"Authorization": f"Bearer {token}"}
files = {"image": open("avatar.jpg", "rb")}

response = requests.put(url, headers=headers, files=files)
data = response.json()
print(f"Avatar actualizado: {data['avatar_url']}")
```

#### Notas

1. **Procesamiento automático**: La imagen se redimensiona automáticamente a 400x400 píxeles y se convierte a formato JPG para optimizar el almacenamiento.

2. **Eliminación del avatar anterior**: Si el usuario ya tenía un avatar, este se elimina automáticamente de S3 al subir uno nuevo.

3. **Transaccionalidad**: Si la actualización en la base de datos falla después de subir la imagen, el endpoint intenta eliminar la imagen recién subida para mantener la consistencia.

4. **Rate limiting**: Este endpoint está sujeto a límites de tasa para prevenir abuso.

5. **Validación de seguridad**: El endpoint valida:
   - El tipo MIME del archivo
   - Los "magic bytes" del archivo para prevenir ataques
   - Que la imagen sea válida y no esté corrupta
   - El tamaño del archivo

6. **Uso con GraphQL**: Después de actualizar el avatar con este endpoint, puedes consultar el usuario actualizado usando la query GraphQL `me`:
   ```graphql
   query {
     me(jwt: "token") {
       id
       name
       avatar
       avatarUrl
     }
   }
   ```
