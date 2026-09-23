import 'package:flutter/material.dart';
import '../models/models.dart';
import '../widgets/widgets.dart';

class ImmersiveLabelScreen extends StatelessWidget {
  final String? imagePath;
  final String? albumEntryId;
  final List<Label> labels;
  final String? model;
  final int? latencyMs;
  final Function(int, Label)? onLabelChanged;
  final VoidCallback? onReset;
  final VoidCallback? onOpenAlbum;
  final VoidCallback? onSave;
  final VoidCallback? onDelete;
  final bool showAppBar;
  final String title;
  final bool hasUnsavedChanges;

  const ImmersiveLabelScreen({
    super.key,
    this.imagePath,
    this.albumEntryId,
    required this.labels,
    this.model,
    this.latencyMs,
    this.onLabelChanged,
    this.onReset,
    this.onOpenAlbum,
    this.onSave,
    this.onDelete,
    this.showAppBar = true,
    this.title = '拍照學英文',
    this.hasUnsavedChanges = false,
  });

  void _showLabelDetail(BuildContext context, Label label, int index) {
    LabelDetailSheet.show(
      context,
      label,
      onChanged: onLabelChanged != null
          ? (updatedLabel) {
              onLabelChanged!(index, updatedLabel);
            }
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D1A),
      extendBodyBehindAppBar: true,
      appBar: showAppBar ? _buildAppBar(context) : null,
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: SizedBox(
              height: MediaQuery.of(context).size.height * 0.55,
              child: Stack(
                children: [
                  ImmersivePhotoView(
                    imagePath: imagePath,
                    albumEntryId: albumEntryId,
                    labels: labels,
                    onLabelTap: (label) {
                      final index = labels.indexOf(label);
                      _showLabelDetail(context, label, index >= 0 ? index : 0);
                    },
                  ),
                  if (model != null || latencyMs != null)
                    Positioned(
                      bottom: 16,
                      right: 16,
                      child: _buildMetaBadge(),
                    ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: WordListSection(
              labels: labels,
              onLabelTap: (label) {
                final index = labels.indexOf(label);
                _showLabelDetail(context, label, index >= 0 ? index : 0);
              },
              onLabelChanged: onLabelChanged,
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    return AppBar(
      backgroundColor: Colors.transparent,
      elevation: 0,
      title: Text(
        title,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w600,
        ),
      ),
      iconTheme: const IconThemeData(color: Colors.white),
      actions: [
        if (onOpenAlbum != null)
          IconButton(
            icon: const Icon(Icons.photo_album),
            onPressed: onOpenAlbum,
            tooltip: '我的相簿',
          ),
        if (hasUnsavedChanges && onSave != null)
          IconButton(
            icon: const Icon(Icons.save),
            onPressed: onSave,
            tooltip: '儲存',
          ),
        if (onDelete != null)
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: onDelete,
            tooltip: '刪除',
          ),
        if (onReset != null)
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: onReset,
            tooltip: '重新開始',
          ),
      ],
    );
  }

  Widget _buildMetaBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (model != null)
            Text(
              model!,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 11,
              ),
            ),
          if (model != null && latencyMs != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Container(
                width: 3,
                height: 3,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.5),
                  shape: BoxShape.circle,
                ),
              ),
            ),
          if (latencyMs != null)
            Text(
              '${latencyMs}ms',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 11,
              ),
            ),
        ],
      ),
    );
  }
}
