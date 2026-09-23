import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/services.dart';

class ImmersivePhotoView extends StatelessWidget {
  final String? imagePath;
  final String? albumEntryId;
  final List<Label> labels;
  final ValueChanged<Label> onLabelTap;

  const ImmersivePhotoView({
    super.key,
    this.imagePath,
    this.albumEntryId,
    required this.labels,
    required this.onLabelTap,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return Stack(
          fit: StackFit.expand,
          children: [
            _buildImage(),
            _buildGradientOverlay(),
            _buildChips(context, constraints),
          ],
        );
      },
    );
  }

  Widget _buildImage() {
    if (kIsWeb && albumEntryId != null) {
      return FutureBuilder<dynamic>(
        future: AlbumService.getImageBytes(albumEntryId!),
        builder: (context, snapshot) {
          if (snapshot.hasData && snapshot.data != null) {
            return Image.memory(
              snapshot.data,
              fit: BoxFit.cover,
              width: double.infinity,
              height: double.infinity,
            );
          }
          return Container(color: Colors.black);
        },
      );
    }

    if (imagePath != null) {
      return Image.file(
        File(imagePath!),
        fit: BoxFit.cover,
        width: double.infinity,
        height: double.infinity,
        errorBuilder: (context, error, stackTrace) {
          return Container(color: Colors.black);
        },
      );
    }

    return Container(color: Colors.black);
  }

  Widget _buildGradientOverlay() {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.black.withValues(alpha: 0.1),
            Colors.black.withValues(alpha: 0.3),
            Colors.black.withValues(alpha: 0.6),
          ],
          stops: const [0.0, 0.5, 1.0],
        ),
      ),
    );
  }

  Widget _buildChips(BuildContext context, BoxConstraints constraints) {
    if (labels.isEmpty) return const SizedBox.shrink();

    // TODO(bbox): Use pipe label bbox coordinates when available.
    // Currently using evenly spread positions as placeholders.
    final positions = _generateChipPositions(labels.length, constraints);

    return Stack(
      children: [
        for (int i = 0; i < labels.length; i++)
          Positioned(
            left: positions[i].dx,
            top: positions[i].dy,
            child: _FrostedChip(
              label: labels[i],
              onTap: () => onLabelTap(labels[i]),
            ),
          ),
      ],
    );
  }

  List<Offset> _generateChipPositions(int count, BoxConstraints constraints) {
    // TODO(bbox): Replace with actual bbox coordinates from API when available.
    // Current implementation spreads chips evenly across the image area.
    final random = math.Random(42); // Fixed seed for consistent placement
    final positions = <Offset>[];
    final safeArea = EdgeInsets.fromLTRB(
      16,
      constraints.maxHeight * 0.15,
      16,
      constraints.maxHeight * 0.35,
    );

    final availableWidth = constraints.maxWidth - safeArea.left - safeArea.right - 100;
    final availableHeight = constraints.maxHeight - safeArea.top - safeArea.bottom;

    for (int i = 0; i < count; i++) {
      final row = i ~/ 2;
      final col = i % 2;
      final baseX = safeArea.left + (col * availableWidth / 2) + random.nextDouble() * 40;
      final baseY = safeArea.top + (row * availableHeight / 3) + random.nextDouble() * 30;
      positions.add(Offset(baseX.clamp(16, constraints.maxWidth - 120), baseY));
    }

    return positions;
  }
}

class _FrostedChip extends StatelessWidget {
  final Label label;
  final VoidCallback onTap;

  const _FrostedChip({
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label.en,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 15,
                    shadows: [
                      Shadow(
                        color: Colors.black54,
                        blurRadius: 4,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Icon(
                  Icons.volume_up,
                  size: 16,
                  color: Colors.white.withValues(alpha: 0.9),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
