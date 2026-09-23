import 'package:flutter/material.dart';
import '../models/models.dart';

class ErrorView extends StatelessWidget {
  final LabelError error;
  final VoidCallback onRetry;

  const ErrorView({
    super.key,
    required this.error,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              _getIconForCode(error.code),
              size: 64,
              color: Colors.red[300],
            ),
            const SizedBox(height: 16),
            Text(
              error.localizedMessage,
              style: const TextStyle(fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              '錯誤代碼：${error.code}',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey[600],
              ),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重試'),
            ),
          ],
        ),
      ),
    );
  }

  IconData _getIconForCode(String code) {
    switch (code) {
      case 'timeout':
        return Icons.timer_off;
      case 'upstream':
      case 'unavailable':
        return Icons.cloud_off;
      case 'bad_image':
        return Icons.broken_image;
      case 'queue_full':
        return Icons.hourglass_full;
      case 'network':
        return Icons.wifi_off;
      default:
        return Icons.error_outline;
    }
  }
}
