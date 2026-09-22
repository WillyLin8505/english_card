import 'dart:ui';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/tts_service.dart';

class WordListSection extends StatelessWidget {
  final List<Label> labels;
  final ValueChanged<Label> onLabelTap;
  final Function(int, Label)? onLabelChanged;

  const WordListSection({
    super.key,
    required this.labels,
    required this.onLabelTap,
    this.onLabelChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildHeader(context),
          _buildWordList(),
          if (_hasExamples) _buildAllSentencesSection(),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  bool get _hasExamples => labels.any((l) => l.examples.isNotEmpty);

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
      child: Row(
        children: [
          Container(
            width: 4,
            height: 24,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Colors.blue, Colors.purple],
              ),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          const Text(
            '全部單字整理',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const Spacer(),
          Text(
            '${labels.length} 個單字',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.5),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWordList() {
    return ListView.separated(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: labels.length,
      separatorBuilder: (context, index) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        return _WordCard(
          label: labels[index],
          index: index,
          onTap: () => onLabelTap(labels[index]),
          onChanged: onLabelChanged != null
              ? (label) => onLabelChanged!(index, label)
              : null,
        );
      },
    );
  }

  Widget _buildAllSentencesSection() {
    final allExamples = <MapEntry<Label, ExampleSentence>>[];
    for (final label in labels) {
      for (final example in label.examples) {
        allExamples.add(MapEntry(label, example));
      }
    }

    if (allExamples.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
          child: Row(
            children: [
              Container(
                width: 4,
                height: 24,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Colors.orange, Colors.red],
                  ),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 12),
              const Text(
                '所有例句',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        ListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: allExamples.length,
          itemBuilder: (context, index) {
            final entry = allExamples[index];
            return _SentenceCard(
              label: entry.key,
              example: entry.value,
            );
          },
        ),
      ],
    );
  }
}

class _WordCard extends StatefulWidget {
  final Label label;
  final int index;
  final VoidCallback onTap;
  final ValueChanged<Label>? onChanged;

  const _WordCard({
    required this.label,
    required this.index,
    required this.onTap,
    this.onChanged,
  });

  @override
  State<_WordCard> createState() => _WordCardState();
}

class _WordCardState extends State<_WordCard> {
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

  void _toggleEdit() {
    if (_isEditing && widget.onChanged != null) {
      final newLabel = widget.label.copyWith(
        en: _enController.text.trim().isNotEmpty
            ? _enController.text.trim()
            : widget.label.en,
        zh: _zhController.text.trim().isNotEmpty ? _zhController.text.trim() : null,
      );
      widget.onChanged!(newLabel);
    }
    setState(() => _isEditing = !_isEditing);
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 5, sigmaY: 5),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.1),
            ),
          ),
          child: _isEditing ? _buildEditMode() : _buildDisplayMode(),
        ),
      ),
    );
  }

  Widget _buildDisplayMode() {
    return InkWell(
      onTap: widget.onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.blue.withValues(alpha: 0.3),
                    Colors.purple.withValues(alpha: 0.3),
                  ],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: Text(
                  '${widget.index + 1}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        widget.label.en,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (widget.label.ipa != null) ...[
                        const SizedBox(width: 8),
                        Text(
                          widget.label.ipa!,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.5),
                            fontSize: 14,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (widget.label.zh != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      widget.label.zh!,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.7),
                        fontSize: 15,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              icon: Icon(
                Icons.volume_up,
                color: Colors.white.withValues(alpha: 0.7),
              ),
              onPressed: () => TtsService.speak(widget.label.en),
            ),
            if (widget.onChanged != null)
              IconButton(
                icon: Icon(
                  Icons.edit,
                  color: Colors.white.withValues(alpha: 0.5),
                  size: 20,
                ),
                onPressed: _toggleEdit,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildEditMode() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          TextField(
            controller: _enController,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: 'English',
              labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
              enabledBorder: OutlineInputBorder(
                borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
                borderRadius: BorderRadius.circular(8),
              ),
              focusedBorder: OutlineInputBorder(
                borderSide: const BorderSide(color: Colors.white),
                borderRadius: BorderRadius.circular(8),
              ),
              isDense: true,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _zhController,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: '中文（選填）',
              labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
              enabledBorder: OutlineInputBorder(
                borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
                borderRadius: BorderRadius.circular(8),
              ),
              focusedBorder: OutlineInputBorder(
                borderSide: const BorderSide(color: Colors.white),
                borderRadius: BorderRadius.circular(8),
              ),
              isDense: true,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: () => setState(() => _isEditing = false),
                child: Text(
                  '取消',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.7)),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _toggleEdit,
                child: const Text('儲存'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SentenceCard extends StatelessWidget {
  final Label label;
  final ExampleSentence example;

  const _SentenceCard({
    required this.label,
    required this.example,
  });

  @override
  Widget build(BuildContext context) {
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
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.blue.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  label.en,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => TtsService.speak(example.en),
                child: Icon(
                  Icons.volume_up,
                  size: 18,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            example.en,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 15,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 6),
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
