/// License page URL for a license name as stored in the pack
/// (e.g. "CC BY-SA 4.0", "CC BY 3.0 US", "CC0"). Null when there is no
/// Creative Commons page to link (public domain, unknown names).
String? licenseUrlFor(String? license) {
  final s = (license ?? '').toUpperCase();
  if (s.contains('CC0')) {
    return 'https://creativecommons.org/publicdomain/zero/1.0/';
  }
  final m = RegExp(r'CC (BY(?:-SA)?) ([\d.]+)( US| FR)?').firstMatch(s);
  if (m == null) return null;
  final path = m.group(1)!.toLowerCase();
  final region = m.group(3)?.trim().toLowerCase();
  return 'https://creativecommons.org/licenses/$path/${m.group(2)}/'
      '${region == null ? '' : '$region/'}';
}
