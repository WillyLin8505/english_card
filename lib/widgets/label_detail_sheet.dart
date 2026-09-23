import 'dart:async';
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

class _LabelDetailSheetState extends State<LabelDetailSheet>
    with SingleTickerProviderStateMixin {
  bool _isPlaying = false;
  bool _isEditing = false;
  late TextEditingController _enController;
  late TextEditingController _zhController;
  late AnimationController _waveformController;
  double _playbackProgress = 0.0;
  Timer? _progressTimer;

  @override
  void initState() {
    super.initState();
    _enController = TextEditingController(text: widget.label.en);
    _zhController = TextEditingController(text: widget.label.zh ?? '');
    _waveformController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
  }

  @override
  void dispose() {
    _enController.dispose();
    _zhController.dispose();
    _waveformController.dispose();
    _progressTimer?.cancel();
    super.dispose();
  }

  Future<void> _playTts() async {
    if (_isPlaying) return;

    setState(() {
      _isPlaying = true;
      _playbackProgress = 0.0;
    });

    _waveformController.repeat();

    // Simulate progress bar
    const duration = Duration(milliseconds: 1800);
    const steps = 30;
    final stepDuration = Duration(milliseconds: duration.inMilliseconds ~/ steps);

    _progressTimer = Timer.periodic(stepDuration, (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        _playbackProgress += 1.0 / steps;
        if (_playbackProgress >= 1.0) {
          _playbackProgress = 1.0;
          timer.cancel();
          _isPlaying = false;
          _waveformController.stop();
          _waveformController.reset();
        }
      });
    });

    await TtsService.speak(widget.label.en);
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
      initialChildSize: 0.7,
      minChildSize: 0.5,
      maxChildSize: 0.92,
      builder: (context, scrollController) {
        return ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 25, sigmaY: 25),
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    const Color(0xFF1E1E2E).withValues(alpha: 0.98),
                    const Color(0xFF12121A).withValues(alpha: 0.99),
                  ],
                ),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.08),
                  width: 1,
                ),
              ),
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(24, 12, 24, 40),
                children: [
                  _buildDragHandle(),
                  const SizedBox(height: 20),
                  _buildHeader(),
                  const SizedBox(height: 28),
                  _buildWaveformPlayer(),
                  const SizedBox(height: 32),
                  _buildExamplesSection(),
                  const SizedBox(height: 28),
                  _buildPhrasesSection(),
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
        width: 48,
        height: 5,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.25),
          borderRadius: BorderRadius.circular(3),
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
                  // Large English word
                  Text(
                    widget.label.en,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 36,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.8,
                      height: 1.1,
                    ),
                  ),
                  // IPA pronunciation - always visible area
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      widget.label.ipa ?? '—',
                      style: TextStyle(
                        color: widget.label.ipa != null
                            ? Colors.white.withValues(alpha: 0.85)
                            : Colors.white.withValues(alpha: 0.4),
                        fontSize: 18,
                        fontStyle: FontStyle.italic,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (widget.onLabelChanged != null)
              Container(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: IconButton(
                  icon: Icon(
                    _isEditing ? Icons.check : Icons.edit_outlined,
                    color: Colors.white.withValues(alpha: 0.7),
                    size: 22,
                  ),
                  onPressed: _toggleEdit,
                ),
              ),
          ],
        ),
        // Chinese translation
        const SizedBox(height: 16),
        Text(
          widget.label.zh ?? '—',
          style: TextStyle(
            color: widget.label.zh != null
                ? Colors.white.withValues(alpha: 0.9)
                : Colors.white.withValues(alpha: 0.4),
            fontSize: 26,
            fontWeight: FontWeight.w500,
          ),
        ),
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
                style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
                decoration: InputDecoration(
                  labelText: 'English',
                  labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
                  enabledBorder: OutlineInputBorder(
                    borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.2)),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderSide: BorderSide(color: Colors.blue.withValues(alpha: 0.6)),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  filled: true,
                  fillColor: Colors.white.withValues(alpha: 0.05),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Container(
              decoration: BoxDecoration(
                color: Colors.blue.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(12),
              ),
              child: IconButton(
                icon: const Icon(Icons.check, color: Colors.white),
                onPressed: _toggleEdit,
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _zhController,
          style: const TextStyle(color: Colors.white, fontSize: 18),
          decoration: InputDecoration(
            labelText: '中文（選填）',
            labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
            enabledBorder: OutlineInputBorder(
              borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.2)),
              borderRadius: BorderRadius.circular(14),
            ),
            focusedBorder: OutlineInputBorder(
              borderSide: BorderSide(color: Colors.blue.withValues(alpha: 0.6)),
              borderRadius: BorderRadius.circular(14),
            ),
            filled: true,
            fillColor: Colors.white.withValues(alpha: 0.05),
          ),
        ),
      ],
    );
  }

  Widget _buildWaveformPlayer() {
    return GestureDetector(
      onTap: _playTts,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              const Color(0xFF3B82F6).withValues(alpha: 0.25),
              const Color(0xFF8B5CF6).withValues(alpha: 0.25),
            ],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.1),
          ),
        ),
        child: Column(
          children: [
            // Waveform visualization
            SizedBox(
              height: 48,
              child: AnimatedBuilder(
                animation: _waveformController,
                builder: (context, child) {
                  return CustomPaint(
                    size: const Size(double.infinity, 48),
                    painter: _WaveformPainter(
                      progress: _playbackProgress,
                      isAnimating: _isPlaying,
                      animationValue: _waveformController.value,
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 14),
            // Progress bar
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: _playbackProgress,
                minHeight: 6,
                backgroundColor: Colors.white.withValues(alpha: 0.15),
                valueColor: AlwaysStoppedAnimation<Color>(
                  _isPlaying ? Colors.blue : Colors.white.withValues(alpha: 0.6),
                ),
              ),
            ),
            const SizedBox(height: 14),
            // Play button row
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _isPlaying
                        ? Colors.blue.withValues(alpha: 0.4)
                        : Colors.white.withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    _isPlaying ? Icons.graphic_eq : Icons.play_arrow_rounded,
                    color: Colors.white,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 14),
                Text(
                  _isPlaying ? '播放中...' : '點擊播放發音',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.9),
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
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
        _buildSectionHeader('✦ 情境例句', Icons.chat_bubble_outline),
        const SizedBox(height: 14),
        if (widget.label.examples.isEmpty)
          _buildEmptyState('尚無例句')
        else
          ...widget.label.examples.map((example) => _buildExampleCard(example)),
      ],
    );
  }

  Widget _buildPhrasesSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('片語', Icons.style_outlined),
        const SizedBox(height: 14),
        if (widget.label.phrases.isEmpty)
          _buildEmptyState('尚無片語')
        else
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: widget.label.phrases.map((phrase) => _buildPhraseChip(phrase)).toList(),
          ),
      ],
    );
  }

  Widget _buildSectionHeader(String title, IconData icon) {
    return Row(
      children: [
        Icon(
          icon,
          size: 18,
          color: Colors.white.withValues(alpha: 0.5),
        ),
        const SizedBox(width: 8),
        Text(
          title,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: 14,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(String text) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          style: BorderStyle.solid,
        ),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: Colors.white.withValues(alpha: 0.35),
          fontSize: 14,
          fontStyle: FontStyle.italic,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }

  Widget _buildExampleCard(ExampleSentence example) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.08),
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
                      fontSize: 16,
                      height: 1.5,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: Colors.blue.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.volume_up_rounded,
                    size: 18,
                    color: Colors.white.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Text(
            example.zh,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.55),
              fontSize: 15,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhraseChip(Phrase phrase) {
    return GestureDetector(
      onTap: () => TtsService.speak(phrase.en),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.1),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  phrase.en,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(width: 6),
                Icon(
                  Icons.volume_up,
                  size: 14,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              phrase.zh,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.5),
                fontSize: 13,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  final double progress;
  final bool isAnimating;
  final double animationValue;

  _WaveformPainter({
    required this.progress,
    required this.isAnimating,
    required this.animationValue,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final barCount = 32;
    final barWidth = size.width / (barCount * 2);
    final maxHeight = size.height * 0.9;
    final minHeight = size.height * 0.15;

    for (var i = 0; i < barCount; i++) {
      final x = (i * 2 + 0.5) * barWidth;
      final normalizedProgress = i / barCount;

      // Base height with some variation
      var heightFactor = 0.3 + 0.4 * _pseudoRandom(i);

      // Add animation when playing
      if (isAnimating) {
        final wave = (animationValue * 2 * 3.14159 + i * 0.3).remainder(3.14159 * 2);
        heightFactor += 0.3 * (0.5 + 0.5 * _sin(wave));
      }

      final barHeight = minHeight + (maxHeight - minHeight) * heightFactor;

      // Color based on progress
      final isPlayed = normalizedProgress <= progress;
      final paint = Paint()
        ..color = isPlayed
            ? Colors.blue.withValues(alpha: 0.9)
            : Colors.white.withValues(alpha: 0.3)
        ..strokeCap = StrokeCap.round
        ..strokeWidth = barWidth * 0.8;

      final startY = (size.height - barHeight) / 2;
      canvas.drawLine(
        Offset(x, startY),
        Offset(x, startY + barHeight),
        paint,
      );
    }
  }

  double _pseudoRandom(int seed) {
    return ((seed * 1103515245 + 12345) % 32768) / 32768.0;
  }

  double _sin(double x) {
    // Simple approximation
    x = x % (3.14159 * 2);
    if (x > 3.14159) x -= 3.14159 * 2;
    return x - (x * x * x) / 6 + (x * x * x * x * x) / 120;
  }

  @override
  bool shouldRepaint(_WaveformPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.isAnimating != isAnimating ||
        oldDelegate.animationValue != animationValue;
  }
}
