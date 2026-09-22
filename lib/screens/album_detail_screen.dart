import 'dart:io';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/services.dart';
import '../widgets/widgets.dart';

class AlbumDetailScreen extends StatefulWidget {
  final AlbumEntry entry;

  const AlbumDetailScreen({super.key, required this.entry});

  @override
  State<AlbumDetailScreen> createState() => _AlbumDetailScreenState();
}

class _AlbumDetailScreenState extends State<AlbumDetailScreen> {
  late List<Label> _labels;
  bool _hasChanges = false;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _labels = widget.entry.labels.map((l) => l.copyWith()).toList();
  }

  void _updateLabel(int index, Label label) {
    setState(() {
      _labels[index] = label;
      _hasChanges = true;
    });
  }

  Future<void> _saveChanges() async {
    setState(() => _isSaving = true);

    try {
      final updatedEntry = widget.entry.copyWith(labels: _labels);
      await AlbumService.updateEntry(updatedEntry);

      setState(() {
        _hasChanges = false;
        _isSaving = false;
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('已儲存'),
            duration: Duration(seconds: 1),
          ),
        );
      }
    } catch (e) {
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('儲存失敗：$e')),
        );
      }
    }
  }

  Future<void> _confirmDelete() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('刪除照片'),
        content: const Text('確定要刪除這張照片嗎？此操作無法復原。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('刪除'),
          ),
        ],
      ),
    );

    if (confirm == true && mounted) {
      await AlbumService.deleteEntry(widget.entry.id);
      if (mounted) {
        Navigator.pop(context, true);
      }
    }
  }

  Future<bool> _onWillPop() async {
    if (_hasChanges) {
      final result = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('未儲存的變更'),
          content: const Text('你有未儲存的變更，要儲存嗎？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('捨棄'),
            ),
            TextButton(
              onPressed: () async {
                await _saveChanges();
                if (dialogContext.mounted) Navigator.pop(dialogContext, true);
              },
              child: const Text('儲存'),
            ),
          ],
        ),
      );
      return result ?? false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_hasChanges,
      onPopInvokedWithResult: (didPop, result) async {
        if (!didPop) {
          final shouldPop = await _onWillPop();
          if (shouldPop && context.mounted) {
            Navigator.pop(context, true);
          }
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('照片詳情'),
          actions: [
            if (_hasChanges)
              IconButton(
                icon: _isSaving
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save),
                onPressed: _isSaving ? null : _saveChanges,
                tooltip: '儲存',
              ),
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: _confirmDelete,
              tooltip: '刪除',
            ),
          ],
        ),
        body: Column(
          children: [
            _buildImage(),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Row(
                children: [
                  const Text(
                    '標籤',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _formatDateTime(widget.entry.createdAt),
                    style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.only(bottom: 16),
                itemCount: _labels.length,
                itemBuilder: (context, index) {
                  return LabelCard(
                    label: _labels[index],
                    index: index,
                    onChanged: (label) => _updateLabel(index, label),
                    onTapEn: () => TtsService.speak(_labels[index].en),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImage() {
    return Container(
      height: 250,
      margin: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.grey[200],
      ),
      clipBehavior: Clip.antiAlias,
      child: _buildImageContent(),
    );
  }

  Widget _buildImageContent() {
    if (kIsWeb) {
      return FutureBuilder<dynamic>(
        future: AlbumService.getImageBytes(widget.entry.id),
        builder: (context, snapshot) {
          if (snapshot.hasData && snapshot.data != null) {
            return Image.memory(
              snapshot.data,
              fit: BoxFit.cover,
              width: double.infinity,
            );
          }
          return const Center(
            child: Icon(Icons.image, size: 60, color: Colors.grey),
          );
        },
      );
    }

    return Image.file(
      File(widget.entry.imagePath),
      fit: BoxFit.cover,
      width: double.infinity,
      errorBuilder: (context, error, stackTrace) {
        return const Center(
          child: Icon(Icons.broken_image, size: 60, color: Colors.grey),
        );
      },
    );
  }

  String _formatDateTime(DateTime date) {
    return '${date.year}/${date.month.toString().padLeft(2, '0')}/${date.day.toString().padLeft(2, '0')} '
        '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
  }
}
