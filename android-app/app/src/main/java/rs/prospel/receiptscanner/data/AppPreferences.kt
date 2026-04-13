package rs.prospel.receiptscanner.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException

private const val DATASTORE_NAME = "receipt_scanner_settings"

private val Context.dataStore by preferencesDataStore(name = DATASTORE_NAME)

data class AppSettings(
    val baseUrl: String = "http://192.168.10.20:5173/",
    val username: String = "",
    val password: String = "",
    val selectedProjectId: Int? = null,
    val selectedProjectName: String = "",
)

class AppPreferences(private val context: Context) {
    private val baseUrlKey = stringPreferencesKey("base_url")
    private val usernameKey = stringPreferencesKey("username")
    private val passwordKey = stringPreferencesKey("password")
    private val selectedProjectIdKey = intPreferencesKey("selected_project_id")
    private val selectedProjectNameKey = stringPreferencesKey("selected_project_name")

    val settingsFlow: Flow<AppSettings> = context.dataStore.data
        .catch { exception ->
            if (exception is IOException) emit(emptyPreferences()) else throw exception
        }
        .map { prefs ->
            AppSettings(
                baseUrl = prefs[baseUrlKey] ?: "http://192.168.10.20:5173/",
                username = prefs[usernameKey] ?: "",
                password = prefs[passwordKey] ?: "",
                selectedProjectId = prefs[selectedProjectIdKey],
                selectedProjectName = prefs[selectedProjectNameKey] ?: "",
            )
        }

    suspend fun save(settings: AppSettings) {
        context.dataStore.edit { prefs ->
            prefs[baseUrlKey] = settings.baseUrl
            prefs[usernameKey] = settings.username
            prefs[passwordKey] = settings.password
            if (settings.selectedProjectId != null) prefs[selectedProjectIdKey] = settings.selectedProjectId
            else prefs.remove(selectedProjectIdKey)
            if (settings.selectedProjectName.isNotBlank()) prefs[selectedProjectNameKey] = settings.selectedProjectName
            else prefs.remove(selectedProjectNameKey)
        }
    }
}

