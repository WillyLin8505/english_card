import 'label.dart';

class AlbumEntry {
  final String id;
  final DateTime createdAt;
  final String imagePath;
  final List<Label> labels;

  AlbumEntry({
    required this.id,
    required this.createdAt,
    required this.imagePath,
    required this.labels,
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toIso8601String(),
      'image_path': imagePath,
      'labels': labels.map((l) => {'en': l.en, 'zh': l.zh}).toList(),
    };
  }
}
