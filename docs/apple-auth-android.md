# Apple Sign In para Android (Kotlin Compose)

Este documento describe cómo implementar Apple Sign In en Android usando el flujo web con Custom Tabs.

---

## Flujo General

```
Android App → Custom Tab → Apple Sign In → FastAPI Callback → Deep Link → Android App
```

1. Android llama a `GET /apple/start` para obtener la URL de autorización
2. Android abre esa URL en un Custom Tab
3. Usuario se autentica en Apple
4. Apple hace POST a `/apple/callback` con el código
5. FastAPI valida, crea usuario y genera JWT
6. FastAPI redirige a `llegobusiness://auth/callback?token=xxx`
7. Android captura el deep link y guarda el token

---

## Configuración Android

### 1. AndroidManifest.xml - Deep Link

```xml
<activity
    android:name=".ui.auth.AppleAuthActivity"
    android:exported="true"
    android:launchMode="singleTask">
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data
            android:scheme="llegobusiness"
            android:host="auth"
            android:pathPrefix="/callback" />
    </intent-filter>
</activity>
```

### 2. Dependencias (build.gradle.kts)

```kotlin
dependencies {
    implementation("androidx.browser:browser:1.7.0")
    implementation("io.ktor:ktor-client-android:2.3.7")
    implementation("io.ktor:ktor-client-content-negotiation:2.3.7")
    implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.7")
}
```

---

## Implementación Kotlin

### AppleAuthService.kt

```kotlin
package com.llegobusiness.auth

import android.content.Context
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.Serializable

@Serializable
data class AppleAuthStartResponse(
    val auth_url: String,
    val state: String
)

class AppleAuthService(
    private val baseUrl: String = "https://tu-api.com"
) {
    private val client = HttpClient {
        install(ContentNegotiation) {
            json()
        }
    }

    suspend fun startAppleSignIn(context: Context): String {
        // 1. Get auth URL from backend
        val response: AppleAuthStartResponse = client.get("$baseUrl/apple/start").body()
        
        // 2. Open Custom Tab
        val customTabsIntent = CustomTabsIntent.Builder()
            .setShowTitle(true)
            .build()
        
        customTabsIntent.launchUrl(context, Uri.parse(response.auth_url))
        
        // Return state for verification (optional)
        return response.state
    }
}
```

### AppleAuthActivity.kt (Deep Link Handler)

```kotlin
package com.llegobusiness.ui.auth

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.lifecycle.viewmodel.compose.viewModel

class AppleAuthActivity : ComponentActivity() {
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
    }
    
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }
    
    private fun handleIntent(intent: Intent) {
        val uri = intent.data ?: return
        
        // llegobusiness://auth/callback?token=xxx
        // llegobusiness://auth/callback?error=xxx
        
        val token = uri.getQueryParameter("token")
        val error = uri.getQueryParameter("error")
        
        if (token != null) {
            // Success! Save token and navigate to main screen
            saveToken(token)
            navigateToMain()
        } else if (error != null) {
            // Handle error
            showError(error)
        }
        
        finish()
    }
    
    private fun saveToken(token: String) {
        // Save to DataStore or SharedPreferences
        getSharedPreferences("auth", MODE_PRIVATE)
            .edit()
            .putString("access_token", token)
            .apply()
    }
    
    private fun navigateToMain() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        startActivity(intent)
    }
    
    private fun showError(error: String) {
        // Show toast or navigate to login with error
    }
}
```

### AuthViewModel.kt (con Compose)

```kotlin
package com.llegobusiness.ui.auth

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.llegobusiness.auth.AppleAuthService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed class AuthState {
    object Idle : AuthState()
    object Loading : AuthState()
    data class Success(val token: String) : AuthState()
    data class Error(val message: String) : AuthState()
}

class AuthViewModel : ViewModel() {
    private val appleAuthService = AppleAuthService()
    
    private val _authState = MutableStateFlow<AuthState>(AuthState.Idle)
    val authState: StateFlow<AuthState> = _authState
    
    fun signInWithApple(context: Context) {
        viewModelScope.launch {
            _authState.value = AuthState.Loading
            try {
                appleAuthService.startAppleSignIn(context)
                // El resultado llegará via deep link a AppleAuthActivity
            } catch (e: Exception) {
                _authState.value = AuthState.Error(e.message ?: "Error desconocido")
            }
        }
    }
}
```

### LoginScreen.kt (Compose UI)

```kotlin
package com.llegobusiness.ui.auth

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun LoginScreen(
    viewModel: AuthViewModel = viewModel()
) {
    val context = LocalContext.current
    val authState by viewModel.authState.collectAsState()
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Logo
        Image(
            painter = painterResource(id = R.drawable.logo),
            contentDescription = "Logo",
            modifier = Modifier.size(120.dp)
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        // Apple Sign In Button
        Button(
            onClick = { viewModel.signInWithApple(context) },
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color.Black
            ),
            enabled = authState !is AuthState.Loading
        ) {
            if (authState is AuthState.Loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    color = Color.White
                )
            } else {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    // Apple icon
                    Icon(
                        painter = painterResource(id = R.drawable.ic_apple),
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Continuar con Apple",
                        color = Color.White
                    )
                }
            }
        }
        
        // Error message
        if (authState is AuthState.Error) {
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = (authState as AuthState.Error).message,
                color = MaterialTheme.colorScheme.error
            )
        }
    }
}
```

---

## Endpoints FastAPI

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/apple/start` | Inicia el flujo, retorna `auth_url` y `state` |
| POST | `/apple/callback` | Callback de Apple (no llamar directamente) |

### GET /apple/start

**Response:**
```json
{
  "auth_url": "https://appleid.apple.com/auth/authorize?...",
  "state": "random_state_token"
}
```

### Deep Link Response

**Éxito:**
```
llegobusiness://auth/callback?token=eyJhbGciOiJIUzI1NiIs...
```

**Error:**
```
llegobusiness://auth/callback?error=auth_failed&message=...
```

---

## Variables de Entorno Requeridas

```env
APPLE_TEAM_ID=XXXXXXXXXX
APPLE_KEY_ID=K97BJSHM89
APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIGT...tu-llave-en-una-linea...\n-----END PRIVATE KEY-----"
APPLE_WEB_SERVICE_ID=com.llegoweb
APPLE_WEB_REDIRECT_URI=https://tu-api.com/apple/callback
```

### Cómo convertir el archivo .p8 a variable de entorno

El archivo `.p8` tiene este formato:
```
-----BEGIN PRIVATE KEY-----
MIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg...
...varias líneas...
-----END PRIVATE KEY-----
```

Para Railway, convierte los saltos de línea a `\n`:
```bash
# En terminal, ejecuta esto para obtener el valor:
cat secrets/AuthKey_K97BJSHM89.p8 | tr '\n' '~' | sed 's/~$//' | sed 's/~/\\n/g'
```

Luego en Railway, crea la variable `APPLE_PRIVATE_KEY` con ese valor (entre comillas).

---

## Notas Importantes

1. **Primera autorización**: Apple solo envía el nombre/email del usuario la primera vez. Guárdalo bien.

2. **Custom Tabs vs WebView**: Usa Custom Tabs, no WebView. Apple puede bloquear WebViews.

3. **Deep Link**: El scheme `llegobusiness://` debe coincidir exactamente en:
   - AndroidManifest.xml
   - Constante `ANDROID_DEEP_LINK` en `api/endpoints/apple_auth.py`

4. **HTTPS**: El `APPLE_WEB_REDIRECT_URI` debe ser HTTPS en producción.

5. **State Storage**: En producción con múltiples instancias, usa Redis para almacenar los states pendientes.
