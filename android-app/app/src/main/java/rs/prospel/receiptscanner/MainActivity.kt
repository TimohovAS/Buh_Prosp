package rs.prospel.receiptscanner

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import rs.prospel.receiptscanner.network.ProjectResponse
import rs.prospel.receiptscanner.ui.QrScannerCamera
import rs.prospel.receiptscanner.ui.ScannerUiState
import rs.prospel.receiptscanner.ui.ScannerViewModel
import rs.prospel.receiptscanner.ui.summaryText

class MainActivity : ComponentActivity() {
    private val viewModel: ScannerViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val state by viewModel.uiState.collectAsStateWithLifecycle()
                    ReceiptScannerApp(
                        state = state,
                        viewModel = viewModel,
                        onExit = { finish() },
                    )
                }
            }
        }
    }
}

@Composable
private fun ReceiptScannerApp(
    state: ScannerUiState,
    viewModel: ScannerViewModel,
    onExit: () -> Unit,
) {
    val context = LocalContext.current
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.CAMERA,
            ) == PackageManager.PERMISSION_GRANTED
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasCameraPermission = granted
    }

    LaunchedEffect(state.showSetup) {
        if (!state.showSetup && !hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    LaunchedEffect(state.scanEventId) {
        if (state.scanEventId > 0L) {
            playScanFeedback(context)
            if (!state.showSetup && !state.importing && state.qrUrl.isNotBlank()) {
                viewModel.importCurrentQr()
            }
        }
    }

    LaunchedEffect(state.infoMessage) {
        if (!state.infoMessage.isNullOrBlank()) {
            delay(2500L)
            viewModel.clearInfoMessage()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(16.dp),
    ) {
        when {
            state.loading -> LoadingScreen()
            state.showSetup -> SetupScreen(
                state = state,
                onBaseUrlChange = viewModel::onBaseUrlChange,
                onUsernameChange = viewModel::onUsernameChange,
                onPasswordChange = viewModel::onPasswordChange,
                onSelectProject = viewModel::selectProject,
                onConnect = viewModel::connect,
                onSaveAndOpen = viewModel::saveAndOpenScanner,
            )

            else -> ScannerScreen(
                state = state,
                hasCameraPermission = hasCameraPermission,
                onRequestCameraPermission = {
                    permissionLauncher.launch(Manifest.permission.CAMERA)
                },
                onQrDetected = viewModel::onQrDetected,
                onQrUrlChange = viewModel::onQrUrlChanged,
                onImport = viewModel::importCurrentQr,
                onOpenSettings = viewModel::showSetup,
                onExit = onExit,
            )
        }
    }
}

private fun playScanFeedback(context: Context) {
    runCatching {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val manager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
            manager.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(80L, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(80L)
        }
    }

    runCatching {
        val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 85)
        try {
            tone.startTone(ToneGenerator.TONE_PROP_BEEP, 120)
        } finally {
            tone.release()
        }
    }
}

@Composable
private fun LoadingScreen() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "Loading...",
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun SetupScreen(
    state: ScannerUiState,
    onBaseUrlChange: (String) -> Unit,
    onUsernameChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onSelectProject: (ProjectResponse?) -> Unit,
    onConnect: () -> Unit,
    onSaveAndOpen: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Receipt scanner setup",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = "Enter ProspEl server URL, username and password. The app will scan a receipt QR code and send the URL to the current backend.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        MessageBlock(
            infoMessage = state.infoMessage,
            errorMessage = state.errorMessage,
        )

        OutlinedTextField(
            value = state.baseUrl,
            onValueChange = onBaseUrlChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Server URL") },
            singleLine = true,
            placeholder = { Text("http://192.168.10.20:5173/") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        )

        OutlinedTextField(
            value = state.username,
            onValueChange = onUsernameChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Username") },
            singleLine = true,
        )

        OutlinedTextField(
            value = state.password,
            onValueChange = onPasswordChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
        )

        ProjectSelector(
            projects = state.projects,
            selectedProjectId = state.selectedProjectId,
            selectedProjectName = state.selectedProjectName,
            onSelectProject = onSelectProject,
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedButton(
                onClick = onConnect,
                enabled = !state.connecting && !state.importing,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (state.connecting) "Connecting..." else "Connect")
            }

            Button(
                onClick = onSaveAndOpen,
                enabled = !state.connecting && !state.importing,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (state.connecting) "Connecting..." else "Open scanner")
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedCard(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.outlinedCardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
            ),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "How it works",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "1. Connect to ProspEl\n2. Choose default project\n3. Open scanner\n4. Scan the QR code and tap Send URL",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ProjectSelector(
    projects: List<ProjectResponse>,
    selectedProjectId: Int?,
    selectedProjectName: String,
    onSelectProject: (ProjectResponse?) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = "Default project",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Box {
            OutlinedButton(
                onClick = { expanded = true },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    text = selectedProjectName.ifBlank { "No project" },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            DropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
                modifier = Modifier.fillMaxWidth(0.9f),
            ) {
                DropdownMenuItem(
                    text = { Text("No project") },
                    onClick = {
                        expanded = false
                        onSelectProject(null)
                    },
                )
                projects.forEach { project ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                text = project.displayName(),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        },
                        onClick = {
                            expanded = false
                            onSelectProject(project)
                        },
                    )
                }
            }
        }
        if (projects.isEmpty()) {
            Text(
                text = "Projects will load after a successful connection.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else if (selectedProjectId == null) {
            Text(
                text = "Project is optional. You can assign it later from the web app.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ScannerScreen(
    state: ScannerUiState,
    hasCameraPermission: Boolean,
    onRequestCameraPermission: () -> Unit,
    onQrDetected: (String) -> Unit,
    onQrUrlChange: (String) -> Unit,
    onImport: () -> Unit,
    onOpenSettings: () -> Unit,
    onExit: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Receipt scanner",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = if (state.selectedProjectName.isBlank()) {
                        "Project: not selected"
                    } else {
                        "Project: ${state.selectedProjectName}"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            TextButton(onClick = onOpenSettings) {
                Text("Settings")
            }
        }

        MessageBlock(
            infoMessage = state.infoMessage,
            errorMessage = state.errorMessage,
        )

        if (!hasCameraPermission) {
            OutlinedCard(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                ),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = "Camera permission required",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = "Allow camera access so the app can scan the QR code on the receipt.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(onClick = onRequestCameraPermission) {
                        Text("Allow camera")
                    }
                }
            }
        } else {
            QrScannerCamera(
                enabled = true,
                onQrDetected = onQrDetected,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(
                        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.25f),
                        shape = RoundedCornerShape(18.dp),
                    ),
            )
        }

        OutlinedTextField(
            value = state.qrUrl,
            onValueChange = onQrUrlChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("QR URL") },
            minLines = 3,
            maxLines = 5,
            placeholder = { Text("Scanned QR link will appear here.") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        )

        state.lastReceipt?.let { receipt ->
            ReceiptResultCard(summary = receipt.summaryText())
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedButton(
                onClick = onExit,
                modifier = Modifier.weight(1f),
            ) {
                Text("Exit")
            }
            Button(
                onClick = onImport,
                enabled = state.qrUrl.isNotBlank() && !state.importing,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (state.importing) "Sending..." else "Send URL")
            }
        }
    }
}

@Composable
private fun ReceiptResultCard(summary: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.55f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = "Last import",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
            Text(
                text = summary,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
    }
}

@Composable
private fun MessageBlock(
    infoMessage: String?,
    errorMessage: String?,
) {
    when {
        !errorMessage.isNullOrBlank() -> {
            StatusCard(
                text = errorMessage,
                background = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.65f),
                foreground = MaterialTheme.colorScheme.onErrorContainer,
            )
        }

        !infoMessage.isNullOrBlank() -> {
            StatusCard(
                text = infoMessage,
                background = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.55f),
                foreground = MaterialTheme.colorScheme.onSecondaryContainer,
            )
        }
    }
}

@Composable
private fun StatusCard(
    text: String,
    background: androidx.compose.ui.graphics.Color,
    foreground: androidx.compose.ui.graphics.Color,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = background),
    ) {
        Text(
            text = text,
            color = foreground,
            modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

private fun ProjectResponse.displayName(): String {
    val codePart = code?.takeIf { it.isNotBlank() }?.let { " - $it" }.orEmpty()
    return "$name$codePart"
}
