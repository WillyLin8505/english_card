import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/tts_service.dart';

class LabelCard extends StatefulWidget {
  final Label label;
  final int index;
  final ValueChanged<Label> onChanged;
  final VoidCallback? onTapEn;

  const LabelCard({
    super.key,
    required this.label,
    required this.index,
    required this.onChanged,
    this.onTapEn,
  });

  @override
  State<LabelCard> createState() => _LabelCardState();
}

class _LabelCardState extends State<LabelCard> {
  late TextEditingController _enController;
  late TextEditingController _zhController;
  bool _isEditing = false;

  @override
  void initState() {
    super.initState();
    _enController = TextEditingController(text: widget.label.en);
    _zhController = TextEditingController(text: widget.label.zh ?? '');
  }

  @override
  void didUpdateWidget(LabelCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.label.en != widget.label.en) {
      _enController.text = widget.label.en;
    }
    if (oldWidget.label.zh != widget.label.zh) {
      _zhController.text = widget.label.zh ?? '';
    }
  }

  @override
  void dispose() {
    _enController.dispose();
    _zhController.dispose();
    super.dispose();
  }

  void _toggleEdit() {
    if (_isEditing) {
      final newLabel = widget.label.copyWith(
        en: _enController.text.trim().isNotEmpty
            ? _enController.text.trim()
            : widget.label.en,
        zh: _zhController.text.trim().isNotEmpty ? _zhController.text.trim() : null,
      );
      widget.onChanged(newLabel);
    }
    setState(() => _isEditing = !_isEditing);
  }

  @override
  Widget build(BuildContext context) {
    final confidence = widget.label.confidence;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Center(
                    child: Text(
                      '${widget.index + 1}',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _isEditing
                      ? _buildEditFields()
                      : _buildDisplayFields(),
                ),
                IconButton(
                  icon: Icon(_isEditing ? Icons.check : Icons.edit),
                  onPressed: _toggleEdit,
                  tooltip: _isEditing ? '儲存' : '編輯',
                ),
              ],
            ),
            if (confidence != null && !_isEditing) ...[
              const SizedBox(height: 8),
              _buildConfidenceBar(confidence),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildDisplayFields() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          onTap: () {
            if (widget.onTapEn != null) {
              widget.onTapEn!();
            } else {
              TtsService.speak(widget.label.en);
            }
          },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.label.en,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(width: 6),
              Icon(
                Icons.volume_up,
                size: 18,
                color: Theme.of(context).colorScheme.primary,
              ),
            ],
          ),
        ),
        if (widget.label.zh != null && widget.label.zh!.isNotEmpty)
          Text(
            widget.label.zh!,
            style: TextStyle(
              fontSize: 14,
              color: Colors.grey[600],
            ),
          ),
      ],
    );
  }

  Widget _buildEditFields() {
    return Column(
      children: [
        TextField(
          controller: _enController,
          decoration: const InputDecoration(
            labelText: 'English',
            isDense: true,
            border: OutlineInputBorder(),
          ),
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _zhController,
          decoration: const InputDecoration(
            labelText: '中文（選填）',
            isDense: true,
            border: OutlineInputBorder(),
          ),
        ),
      ],
    );
  }

  Widget _buildConfidenceBar(double confidence) {
    final percent = (confidence * 100).toInt();
    return Row(
      children: [
        const SizedBox(width: 40),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: confidence,
              minHeight: 6,
              backgroundColor: Colors.grey[200],
            ),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          '$percent%',
          style: TextStyle(
            fontSize: 12,
            color: Colors.grey[600],
          ),
        ),
      ],
    );
  }
}
