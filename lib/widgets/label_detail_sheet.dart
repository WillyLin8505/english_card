import 'dart:ui';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/tts_service.dart';

class LabelDetailSheet extends StatefulWidget {
  final Label label;
  final ValueChanged<Label>? onLabelChanged;

  const LabelDetailSheet({
    super.key,
    required this.label,
    this.onLabelChanged,
  });

  static void show(BuildContext context, Label label, {ValueChanged<Label>? onChanged}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => LabelDetailSheet(
        label: label,
        onLabelChanged: onChanged,
      ),
    );
  }

  @override
  State<LabelDetailSheet> createState() => _LabelDetailSheetState();
}

class _LabelDetailSheetState extends State<LabelDetailSheet> {
  bool _isPlaying = false;
  bool _isEditing = false;
  late TextEditingController _enController;
  late TextEditingController _zhController;

  @override
  void initState() {
    super.initState();
    _enController = TextEditingController(text: widget.label.en);
    _zhController = TextEditingController(text: widget.label.zh ?? '');
  }

  @override
  void dispose() {
    _enController.dispose();
    _zhController.dispose();
    super.dispose();
  }

  Future<void> _playTts() async {
    setState(() => _isPlaying = true);
    await TtsService.speak(widget.label.en);
    await Future.delayed(const Duration(milliseconds: 1500));
    if (mounted) setState(() => _isPlaying = false);
  }

  void _toggleEdit() {
    if (_isEditing && widget.onLabelChanged != null) {
      final newLabel = widget.label.copyWith(
        en: _enController.text.trim().isNotEmpty
            ? _enController.text.trim()
            : widget.label.en,
        zh: _zhController.text.trim().isNotEmpty ? _zhController.text.trim() : null,
      );
      widget.onLabelChanged!(newLabel);
    }
    setState(() => _isEditing = !_isEditing);
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.6,
      minChildSize: 0.4,
      maxChildSize: 0.9,
      builder: (context, scrollController) {
        return ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A2E).withValues(alpha: 0.95),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(24, 12, 24, 32),
                children: [
                  _buildDragHandle(),
                  const SizedBox(height: 16),
                  _buildHeader(),
                  const SizedBox(height: 24),
                  _buildTtsButton(),
                  if (widget.label.examples.isNotEmpty) ...[
                    const SizedBox(height: 28),
                    _buildExamplesSection(),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildDragHandle() {
    return Center(
      child: Container(
        width: 40,
        height: 4,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.3),
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    if (_isEditing) {
      return _buildEditFields();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.label.en,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      letterSpacing: -0.5,
                    ),
                  ),
                  if (widget.label.ipa != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      widget.label.ipa!,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.6),
                        fontSize: 18,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (widget.onLabelChanged != null)
              IconButton(
                icon: Icon(
                  _isEditing ? Icons.check : Icons.edit,
                  color: Colors.white.withValues(alpha: 0.7),
                ),
                onPressed: _toggleEdit,
              ),
          ],
        ),
        if (widget.label.zh != null) ...[
          const SizedBox(height: 12),
          Text(
            widget.label.zh!,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.85),
              fontSize: 22,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildEditFields() {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _enController,
                style: const TextStyle(color: Colors.white, fontSize: 20),
                decoration: InputDecoration(
                  labelText: 'English',
                  labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
                  enabledBorder: OutlineInputBorder(
                    borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderSide: const BorderSide(color: Colors.white),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            IconButton(
              icon: const Icon(Icons.check, color: Colors.white),
              onPressed: _toggleEdit,
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _zhController,
          style: const TextStyle(color: Colors.white, fontSize: 18),
          decoration: InputDecoration(
            labelText: '中文（選填）',
            labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
            enabledBorder: OutlineInputBorder(
              borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
              borderRadius: BorderRadius.circular(12),
            ),
            focusedBorder: OutlineInputBorder(
              borderSide: const BorderSide(color: Colors.white),
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTtsButton() {
    return GestureDetector(
      onTap: _playTts,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              Colors.blue.withValues(alpha: 0.3),
              Colors.purple.withValues(alpha: 0.3),
            ],
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              child: Icon(
                _isPlaying ? Icons.graphic_eq : Icons.play_circle_filled,
                color: Colors.white,
                size: 28,
              ),
            ),
            const SizedBox(width: 12),
            Text(
              _isPlaying ? '播放中...' : '點擊播放發音',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildExamplesSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '例句',
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: 14,
            fontWeight: FontWeight.w600,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 12),
        ...widget.label.examples.map((example) => _buildExampleCard(example)),
      ],
    );
  }

  Widget _buildExampleCard(ExampleSentence example) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.1),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () => TtsService.speak(example.en),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    example.en,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      height: 1.4,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.volume_up,
                  size: 18,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            example.zh,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.6),
              fontSize: 14,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }
}
