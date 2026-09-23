import 'label.dart';

class AlbumEntry {
  final String id;
  final DateTime createdAt;
  final String imagePath;
  List<Label> labels;

  AlbumEntry({
    required this.id,
    required this.createdAt,
    required this.imagePath,
    required this.labels,
  });

  factory AlbumEntry.fromJson(Map<String, dynamic> json) {
    final labelsJson = json['labels'] as List<dynamic>?;
    return AlbumEntry(
      id: json['id'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      imagePath: json['image_path'] as String,
      labels: labelsJson
              ?.map((e) => Label.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toIso8601String(),
      'image_path': imagePath,
      'labels': labels.map((l) => l.toJson()).toList(),
    };
  }

  AlbumEntry copyWith({
    String? id,
    DateTime? createdAt,
    String? imagePath,
    List<Label>? labels,
  }) {
    return AlbumEntry(
      id: id ?? this.id,
      createdAt: createdAt ?? this.createdAt,
      imagePath: imagePath ?? this.imagePath,
      labels: labels ?? this.labels,
    );
  }
}
