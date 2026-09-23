import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/services.dart';
import 'immersive_label_screen.dart';

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
            backgroundColor: Color(0xFF1A1A2E),
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
      builder: (dialogContext) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        title: const Text('刪除照片', style: TextStyle(color: Colors.white)),
        content: const Text(
          '確定要刪除這張照片嗎？此操作無法復原。',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
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
          backgroundColor: const Color(0xFF1A1A2E),
          title: const Text('未儲存的變更', style: TextStyle(color: Colors.white)),
          content: const Text(
            '你有未儲存的變更，要儲存嗎？',
            style: TextStyle(color: Colors.white70),
          ),
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
      child: ImmersiveLabelScreen(
        imagePath: widget.entry.imagePath,
        albumEntryId: widget.entry.id,
        labels: _labels,
        onLabelChanged: _updateLabel,
        onSave: _hasChanges ? (_isSaving ? null : _saveChanges) : null,
        onDelete: _confirmDelete,
        title: '照片詳情',
        hasUnsavedChanges: _hasChanges,
      ),
    );
  }
}
