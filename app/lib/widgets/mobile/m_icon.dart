import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// SVG icons exported from the Figma mobile screens
/// (assets/figma/mobile/). Each keeps the colour and size it has in the
/// mock; [tint] recolours one, used only for the 拍照 / 設定 tabs'
/// selected state, which the mock never shows (the other tabs' selected
/// variants differ from the unselected ones only by that stroke colour).
enum MIcon {
  arrowLeft('arrow_left'),
  share('share'),
  starOffNav('star_off_nav'),
  star('star'),
  starOff('star_off'),
  audioWaveform('audio_waveform'),
  audioWaveformWhite('audio_waveform_white'),
  plusWhite('plus_white'),
  focalDot('focal_dot'),
  difficultyGauge('difficulty_gauge'),
  gaugeNeedle('gauge_needle'),
  search20('search_20'),
  cameraWhite('camera_white'),
  xCircle('x_circle'),
  galleryBlue('gallery_blue'),
  settings20('settings_20'),
  pulseDot('pulse_dot'),
  gallery20('gallery_20'),
  zap('zap'),
  chevronUp('chevron_up'),
  tabCamera('tab_camera'),
  tabGallery('tab_gallery'),
  tabGalleryActive('tab_gallery_active'),
  tabBook('tab_book'),
  tabBookActive('tab_book_active'),
  tabCards('tab_cards'),
  tabCardsActive('tab_cards_active'),
  tabSettings('tab_settings'),
  statusSignal('status_signal'),
  statusWifi('status_wifi'),
  statusBattery('status_battery');

  final String file;
  const MIcon(this.file);

  String get asset => 'assets/figma/mobile/$file.svg';
}

class MSvg extends StatelessWidget {
  final MIcon icon;
  final double width;
  final double height;
  final Color? tint;

  const MSvg(this.icon, {super.key, required double size, this.tint})
      : width = size,
        height = size;

  const MSvg.sized(this.icon,
      {super.key, required this.width, required this.height, this.tint});

  @override
  Widget build(BuildContext context) => SvgPicture.asset(
        icon.asset,
        width: width,
        height: height,
        colorFilter:
            tint == null ? null : ColorFilter.mode(tint!, BlendMode.srcIn),
      );
}
