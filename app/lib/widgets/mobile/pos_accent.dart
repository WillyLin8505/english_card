import 'package:flutter/material.dart';

import '../../services/photo_word_grid.dart';
import '../../theme/mobile_theme.dart';

/// The colour a label of this part of speech wears (null = no accent).
Color? posAccent(String pos, String word) => switch (gridRowFor(pos, word)) {
      GridRow.noun => MColors.primary,
      GridRow.adjective => MColors.success,
      GridRow.verb => const Color(0xFFE8913A),
      GridRow.phrase => const Color(0xFF8B5CF6),
      _ => null,
    };
