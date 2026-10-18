package com.example.photo_english_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

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
    }
}
