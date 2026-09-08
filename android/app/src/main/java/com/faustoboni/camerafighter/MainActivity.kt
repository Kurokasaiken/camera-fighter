package com.faustoboni.camerafighter

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.pose.PoseDetection
import com.google.mlkit.vision.pose.PoseDetector
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions
import org.msgpack.core.MessagePack
import java.io.ByteArrayOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : AppCompatActivity() {

    companion object {
        const val TAG = "CameraFighter"
        const val REQUEST_CODE_PERMISSIONS = 10
        val REQUIRED_PERMISSIONS = arrayOf(Manifest.permission.CAMERA)

        // Cambia con l'indirizzo IP del tuo Mac
        const val MAC_IP = "192.168.1.160"
        const val MAC_PORT = 5005
    }

    private lateinit var viewFinder: PreviewView
    private lateinit var statusText: TextView
    private lateinit var poseDetector: PoseDetector
    private lateinit var cameraExecutor: ExecutorService
    private val sequence = AtomicInteger(0)
    private val socket = DatagramSocket()
    private val macAddress: InetAddress by lazy { InetAddress.getByName(MAC_IP) }
    private val sendExecutor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        viewFinder = findViewById(R.id.previewView)
        statusText = findViewById(R.id.statusText)

        if (allPermissionsGranted()) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(
                this,
                REQUIRED_PERMISSIONS,
                REQUEST_CODE_PERMISSIONS
            )
        }

        val options = PoseDetectorOptions.Builder()
            .setDetectorMode(PoseDetectorOptions.STREAM_MODE)
            .build()
        poseDetector = PoseDetection.getClient(options)

        cameraExecutor = Executors.newSingleThreadExecutor()
    }

    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(baseContext, it) == PackageManager.PERMISSION_GRANTED
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CODE_PERMISSIONS) {
            if (allPermissionsGranted()) {
                startCamera()
            } else {
                Toast.makeText(this, "Permessi camera richiesti", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder()
                .build()
                .also {
                    it.setSurfaceProvider(viewFinder.surfaceProvider)
                }

            val imageAnalysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor) { imageProxy ->
                        processImage(imageProxy)
                    }
                }

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageAnalysis
                )
            } catch (exc: Exception) {
                Log.e(TAG, "Errore bind camera", exc)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun processImage(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image ?: run {
            imageProxy.close()
            return
        }
        val image = InputImage.fromMediaImage(
            mediaImage,
            imageProxy.imageInfo.rotationDegrees
        )

        poseDetector.process(image)
            .addOnSuccessListener { pose ->
                sendPose(pose, imageProxy.width, imageProxy.height)
                runOnUiThread {
                    statusText.text = "Frame #${sequence.get()} inviato"
                }
                imageProxy.close()
            }
            .addOnFailureListener { e ->
                Log.e(TAG, "Pose detection failed", e)
                imageProxy.close()
            }
    }

    private fun sendPose(pose: com.google.mlkit.vision.pose.Pose, imgWidth: Int, imgHeight: Int) {
        val landmarks = pose.allPoseLandmarks.map {
            // T-005 (PLAN-048e): aggiunta z da position3D (stima ML Kit,
            // NON accurata — il gate lato Mac la usa solo se la varianza
            // per-landmark e' sotto soglia pre-registrata).
            listOf(
                it.position.x / imgWidth,
                it.position.y / imgHeight,
                it.inFrameLikelihood,
                it.position3D.z
            )
        }

        val baos = ByteArrayOutputStream()
        MessagePack.newDefaultPacker(baos).use { packer ->
            packer.packMapHeader(3)
            packer.packString("ts")
            packer.packLong(android.os.SystemClock.elapsedRealtime())
            packer.packString("seq")
            packer.packInt(sequence.incrementAndGet())
            packer.packString("landmarks")
            packer.packArrayHeader(landmarks.size)
            for (lm in landmarks) {
                packer.packArrayHeader(4)
                packer.packFloat(lm[0])
                packer.packFloat(lm[1])
                packer.packFloat(lm[2])
                packer.packFloat(lm[3])
            }
        }
        val bytes = baos.toByteArray()

        sendExecutor.execute {
            try {
                val packet = DatagramPacket(bytes, bytes.size, macAddress, MAC_PORT)
                socket.send(packet)
            } catch (e: Exception) {
                Log.e(TAG, "Errore invio UDP", e)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        sendExecutor.shutdown()
        socket.close()
        poseDetector.close()
    }
}
