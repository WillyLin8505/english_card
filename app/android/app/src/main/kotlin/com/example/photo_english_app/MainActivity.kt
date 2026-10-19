package com.example.photo_english_app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.Rect
import android.media.ExifInterface
import android.os.Build
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayInputStream

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // No on-device classifier on Android yet (問題回報 #265: iOS uses
        // Apple Vision). The app then says so instead of waiting for a server.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "photo_english/local_vision")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "available" -> result.success(false)
                    else -> result.notImplemented()
                }
            }
        // On-device text reading for lib/services/text_scan.dart (問題回報
        // #324): ML Kit's bundled Latin recognizer. Same answer as iOS:
        // [{text, confidence, box: [x, y, w, h], words: [{text, box}]}],
        // boxes as fractions of the upright image, origin top left.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "photo_english/text_recognition")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "available" -> result.success(true)
                    "recognize" -> {
                        val bytes = call.argument<ByteArray>("image")
                        val bitmap = bytes?.let { upright(it) }
                        if (bitmap == null) {
                            result.error("bad_args", "image bytes required", null)
                            return@setMethodCallHandler
                        }
                        recognize(bitmap, result)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    /// The picture decoded, turned as its EXIF says and at most 2048 px on
    /// its long side (faster, and plenty for printed text).
    private fun upright(bytes: ByteArray): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 2048) sample *= 2
        val bitmap = BitmapFactory.decodeByteArray(
            bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample }
        ) ?: return null
        val degrees = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            when (ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(
                ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL
            )) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> 0f
            }
        } else 0f
        if (degrees == 0f) return bitmap
        val m = Matrix().apply { postRotate(degrees) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, m, true)
    }

    private fun recognize(bitmap: Bitmap, result: MethodChannel.Result) {
        val w = bitmap.width.toDouble()
        val h = bitmap.height.toDouble()
        fun box(r: Rect?): List<Double>? = r?.let {
            listOf(it.left / w, it.top / h, it.width() / w, it.height() / h)
        }
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        recognizer.process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener { text ->
                val lines = mutableListOf<Map<String, Any>>()
                for (block in text.textBlocks) {
                    for (line in block.lines) {
                        val lineBox = box(line.boundingBox) ?: continue
                        lines.add(
                            mapOf(
                                "text" to line.text,
                                "confidence" to line.confidence.toDouble(),
                                "box" to lineBox,
                                "words" to line.elements.mapNotNull { e ->
                                    box(e.boundingBox)?.let { mapOf("text" to e.text, "box" to it) }
                                },
                            )
                        )
                    }
                }
                result.success(lines)
            }
            .addOnFailureListener { e -> result.error("mlkit", e.message, null) }
            .addOnCompleteListener { recognizer.close() }
    }
}
