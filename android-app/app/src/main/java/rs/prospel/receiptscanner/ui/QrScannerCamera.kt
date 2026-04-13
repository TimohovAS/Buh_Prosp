package rs.prospel.receiptscanner.ui

import android.annotation.SuppressLint
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong

@Composable
fun QrScannerCamera(
    modifier: Modifier = Modifier,
    enabled: Boolean,
    onQrDetected: (String) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val previewView = remember {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            cameraExecutor.shutdown()
        }
    }

    val latestHitAt = remember { AtomicLong(0L) }
    val latestValueHash = remember { AtomicLong(0L) }

    LaunchedEffect(enabled) {
        if (!enabled) {
            ProcessCameraProvider.getInstance(context).get().unbindAll()
        }
    }

    LaunchedEffect(enabled, previewView, lifecycleOwner) {
        if (enabled) {
            bindCamera(
                previewView = previewView,
                lifecycleOwner = lifecycleOwner,
                context = context,
                cameraExecutor = cameraExecutor,
                latestHitAt = latestHitAt,
                latestValueHash = latestValueHash,
                onQrDetected = onQrDetected,
            )
        }
    }

    if (!enabled) {
        Box(
            modifier = modifier.background(
                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
                shape = RoundedCornerShape(16.dp),
            ),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "Camera is turned off.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp),
            )
        }
        return
    }

    AndroidView(
        factory = { previewView },
        modifier = modifier,
    )
}

@SuppressLint("UnsafeOptInUsageError")
private fun bindCamera(
    previewView: PreviewView,
    lifecycleOwner: androidx.lifecycle.LifecycleOwner,
    context: android.content.Context,
    cameraExecutor: ExecutorService,
    latestHitAt: AtomicLong,
    latestValueHash: AtomicLong,
    onQrDetected: (String) -> Unit,
) {
    val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
    cameraProviderFuture.addListener(
        {
            val cameraProvider = cameraProviderFuture.get()
            cameraProvider.unbindAll()

            val preview = Preview.Builder().build().apply {
                surfaceProvider = previewView.surfaceProvider
            }

            val options = BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build()
            val scanner = BarcodeScanning.getClient(options)

            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()

            analysis.setAnalyzer(cameraExecutor) { imageProxy ->
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return@setAnalyzer
                }

                val image = InputImage.fromMediaImage(
                    mediaImage,
                    imageProxy.imageInfo.rotationDegrees,
                )

                scanner.process(image)
                    .addOnSuccessListener { barcodes ->
                        val qr = barcodes
                            .firstOrNull { !it.rawValue.isNullOrBlank() }
                            ?.rawValue
                            ?.trim()
                            .orEmpty()

                        if (qr.isNotBlank()) {
                            val now = System.currentTimeMillis()
                            val hash = qr.hashCode().toLong()
                            val lastAt = latestHitAt.get()
                            val lastHash = latestValueHash.get()
                            if (hash != lastHash || now - lastAt > 1500) {
                                latestHitAt.set(now)
                                latestValueHash.set(hash)
                                onQrDetected(qr)
                            }
                        }
                    }
                    .addOnCompleteListener {
                        imageProxy.close()
                    }
            }

            cameraProvider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                analysis,
            )
        },
        ContextCompat.getMainExecutor(context),
    )
}
