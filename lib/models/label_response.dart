import 'label.dart';

class LabelResponse {
  final bool ok;
  final List<Label>? labels;
  final String? model;
  final int? latencyMs;
  final LabelError? error;

  LabelResponse({
    required this.ok,
    this.labels,
    this.model,
    this.latencyMs,
    this.error,
  });

  factory LabelResponse.fromJson(Map<String, dynamic> json) {
    final ok = json['ok'] as bool;
    if (ok) {
      final labelsJson = json['labels'] as List<dynamic>?;
      return LabelResponse(
        ok: true,
        labels: labelsJson
            ?.map((e) => Label.fromJson(e as Map<String, dynamic>))
            .toList(),
        model: json['model'] as String?,
        latencyMs: json['latency_ms'] as int?,
      );
    } else {
      final errorJson = json['error'] as Map<String, dynamic>?;
      return LabelResponse(
        ok: false,
        error: errorJson != null ? LabelError.fromJson(errorJson) : null,
      );
    }
  }
}

class LabelError {
  final String code;
  final String message;

  LabelError({required this.code, required this.message});

  factory LabelError.fromJson(Map<String, dynamic> json) {
    return LabelError(
      code: json['code'] as String? ?? 'unknown',
      message: json['message'] as String? ?? '未知錯誤',
    );
  }

  String get localizedMessage {
    switch (code) {
      case 'timeout':
        return '請求逾時，請稍後再試';
      case 'upstream':
        return '上游服務錯誤，請稍後再試';
      case 'bad_image':
        return '圖片格式錯誤，請選擇其他照片';
      case 'queue_full':
        return '伺服器繁忙，請稍後再試';
      case 'unavailable':
        return '服務暫時不可用，請稍後再試';
      default:
        return message.isNotEmpty ? message : '發生錯誤（$code）';
    }
  }
}
