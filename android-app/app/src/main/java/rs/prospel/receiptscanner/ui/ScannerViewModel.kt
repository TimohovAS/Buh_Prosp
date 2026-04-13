package rs.prospel.receiptscanner.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import rs.prospel.receiptscanner.data.AppPreferences
import rs.prospel.receiptscanner.data.AppSettings
import rs.prospel.receiptscanner.network.ProjectResponse
import rs.prospel.receiptscanner.network.ProspElRepository
import rs.prospel.receiptscanner.network.ReceiptDetailResponse
import java.math.BigDecimal

data class ScannerUiState(
    val loading: Boolean = true,
    val connecting: Boolean = false,
    val importing: Boolean = false,
    val showSetup: Boolean = true,
    val baseUrl: String = "http://192.168.10.20:5173/",
    val username: String = "",
    val password: String = "",
    val projects: List<ProjectResponse> = emptyList(),
    val selectedProjectId: Int? = null,
    val selectedProjectName: String = "",
    val qrUrl: String = "",
    val infoMessage: String? = null,
    val errorMessage: String? = null,
    val lastReceipt: ReceiptDetailResponse? = null,
)

class ScannerViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = ProspElRepository()
    private val preferences = AppPreferences(application)

    private val _uiState = MutableStateFlow(ScannerUiState())
    val uiState: StateFlow<ScannerUiState> = _uiState.asStateFlow()

    private var accessToken: String? = null

    init {
        viewModelScope.launch {
            val saved = preferences.settingsFlow.first()
            _uiState.update {
                it.copy(
                    loading = false,
                    baseUrl = saved.baseUrl,
                    username = saved.username,
                    password = saved.password,
                    selectedProjectId = saved.selectedProjectId,
                    selectedProjectName = saved.selectedProjectName,
                    showSetup = saved.username.isBlank() || saved.password.isBlank(),
                )
            }

            if (saved.username.isNotBlank() && saved.password.isNotBlank()) {
                connectAndLoadProjects(openScannerOnSuccess = true, saveAfterSuccess = false)
            }
        }
    }

    fun onBaseUrlChange(value: String) {
        _uiState.update { it.copy(baseUrl = value, errorMessage = null) }
    }

    fun onUsernameChange(value: String) {
        _uiState.update { it.copy(username = value, errorMessage = null) }
    }

    fun onPasswordChange(value: String) {
        _uiState.update { it.copy(password = value, errorMessage = null) }
    }

    fun onQrUrlChanged(value: String) {
        _uiState.update { it.copy(qrUrl = value.trim(), errorMessage = null) }
    }

    fun onQrDetected(value: String) {
        val normalized = value.trim()
        if (normalized.isBlank()) return
        _uiState.update { current ->
            if (current.qrUrl == normalized) current else current.copy(qrUrl = normalized)
        }
    }

    fun selectProject(project: ProjectResponse?) {
        _uiState.update {
            it.copy(
                selectedProjectId = project?.id,
                selectedProjectName = project?.displayName().orEmpty(),
            )
        }
    }

    fun showSetup() {
        _uiState.update { it.copy(showSetup = true, errorMessage = null, infoMessage = null) }
    }

    fun connect() {
        viewModelScope.launch {
            connectAndLoadProjects(openScannerOnSuccess = false, saveAfterSuccess = false)
        }
    }

    fun saveAndOpenScanner() {
        viewModelScope.launch {
            connectAndLoadProjects(openScannerOnSuccess = true, saveAfterSuccess = true)
        }
    }

    fun importCurrentQr() {
        viewModelScope.launch {
            val token = accessToken
            val state = _uiState.value
            val url = state.qrUrl.trim()

            if (token.isNullOrBlank()) {
                _uiState.update { it.copy(errorMessage = "Connect to the server first.") }
                return@launch
            }
            if (url.isBlank()) {
                _uiState.update { it.copy(errorMessage = "Scan the QR code first.") }
                return@launch
            }

            _uiState.update { it.copy(importing = true, errorMessage = null, infoMessage = null) }

            try {
                val imported = repository.importReceipt(state.baseUrl, token, url)
                val receipt = if (state.selectedProjectId != null) {
                    repository.assignProject(state.baseUrl, token, imported.receipt.id, state.selectedProjectId)
                } else {
                    imported.receipt
                }

                _uiState.update {
                    it.copy(
                        importing = false,
                        lastReceipt = receipt,
                        infoMessage = if (imported.created) {
                            "Receipt imported."
                        } else {
                            "Receipt already existed in the database."
                        },
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        importing = false,
                        errorMessage = e.message ?: "Failed to import receipt.",
                    )
                }
            }
        }
    }

    private suspend fun connectAndLoadProjects(
        openScannerOnSuccess: Boolean,
        saveAfterSuccess: Boolean,
    ) {
        val state = _uiState.value
        if (state.baseUrl.isBlank() || state.username.isBlank() || state.password.isBlank()) {
            _uiState.update {
                it.copy(
                    errorMessage = "Server URL, username and password are required.",
                    showSetup = true,
                )
            }
            return
        }

        _uiState.update { it.copy(connecting = true, errorMessage = null, infoMessage = null) }

        try {
            val login = repository.login(state.baseUrl, state.username, state.password)
            accessToken = login.accessToken
            val projects = repository.listProjects(state.baseUrl, login.accessToken)

            val selected = projects.firstOrNull { it.id == state.selectedProjectId }
            val projectName = selected?.displayName().orEmpty()

            _uiState.update {
                it.copy(
                    connecting = false,
                    projects = projects,
                    selectedProjectName = if (state.selectedProjectId != null) projectName else "",
                    showSetup = !openScannerOnSuccess,
                    infoMessage = if (openScannerOnSuccess) "Connected. Scanner is ready." else "Connected successfully.",
                    errorMessage = null,
                )
            }

            if (saveAfterSuccess) {
                preferences.save(
                    AppSettings(
                        baseUrl = state.baseUrl,
                        username = state.username,
                        password = state.password,
                        selectedProjectId = _uiState.value.selectedProjectId,
                        selectedProjectName = _uiState.value.selectedProjectName,
                    )
                )
            }
        } catch (e: Exception) {
            accessToken = null
            _uiState.update {
                it.copy(
                    connecting = false,
                    errorMessage = e.message ?: "Failed to connect to the server.",
                    showSetup = true,
                )
            }
        }
    }
}

private fun ProjectResponse.displayName(): String {
    val codePart = code?.takeIf { it.isNotBlank() }?.let { " - $it" }.orEmpty()
    return "$name$codePart"
}

fun ReceiptDetailResponse.summaryText(): String {
    val amountText = try {
        totalAmount.stripTrailingZeros().toPlainString()
    } catch (_: Exception) {
        totalAmount.toString()
    }
    val sellerText = sellerName?.takeIf { it.isNotBlank() } ?: "Unknown seller"
    val invoiceText = invoiceNumber?.takeIf { it.isNotBlank() } ?: "#$id"
    return "$invoiceText | $sellerText | $amountText $currency"
}

fun BigDecimal.formatMoney(): String = try {
    stripTrailingZeros().toPlainString()
} catch (_: Exception) {
    toString()
}
