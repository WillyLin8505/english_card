import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../l10n/ui_text.dart';
import '../services/deck_library.dart';
import '../services/lexicon_pack.dart';
import '../services/word_database_repository.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import 'database_library_screen.dart' show DatabaseImageTile, databaseImageTags;

/// The lexicon pictures of a downloaded 單字集's words (問題回報 #663: a word
/// deck has no photos of its own, so 相片冊 showed nothing for it). One pass
/// over the catalog: a picture is in when an approved tag is one of the
/// deck's words (or the word its pictures come from, [LexEntry.pictureIds]).
List<Map<String, dynamic>> wordDeckImages(
    WordDatabaseRepository repo, InstalledDeck deck, LexiconPack pack,
    {int max = 300}) {
  final ids = <int>{};
  for (final id in deck.entryIds(repo)) {
    final e = repo.entry(id);
    if (e == null) continue;
    final lex = (e.lexemeId == null ? null : pack.byId(e.lexemeId!)) ??
        pack.lookup(e.word, pos: e.pos)?.entry;
    if (lex == null) continue;
    if (lex.pictureIds != null && lex.pictureIds!.isEmpty) continue;
    ids.addAll(lex.pictureIds ?? [lex.id]);
  }
  if (ids.isEmpty) return const [];
  return [
    for (final image in pack.catalogImages)
      if (databaseImageTags(image)
          .any((t) => ids.contains((t['lexeme_id'] as num?)?.toInt())))
        image,
  ].take(max).toList();
}

class WordDeckPhotosScreen extends StatefulWidget {
  final InstalledDeck deck;

  const WordDeckPhotosScreen({super.key, required this.deck});

  @override
  State<WordDeckPhotosScreen> createState() => _WordDeckPhotosScreenState();
}

class _WordDeckPhotosScreenState extends State<WordDeckPhotosScreen> {
  List<Map<String, dynamic>>? _images;

  /// The deck as installed now: an old install gets its full word list
  /// from the server after the page opened (問題回報 #668).
  InstalledDeck get _deck =>
      _library.installedDeck(widget.deck.info.slug) ?? widget.deck;

  final _library = DeckLibrary.instance;

  @override
  void initState() {
    super.initState();
    _library.addListener(_deckChanged);
  }

  @override
  void dispose() {
    _library.removeListener(_deckChanged);
    super.dispose();
  }

  void _deckChanged() {
    if (!mounted) return;
    setState(() => _images = _findImages());
  }

  List<Map<String, dynamic>> _findImages() => wordDeckImages(
      AppScope.of(context).repository, _deck, LexiconPack.instance);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _images ??= _findImages();
  }

  @override
  Widget build(BuildContext context) {
    final images = _images ?? const [];
    return Scaffold(
      backgroundColor: MColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            MNavBar(
              title: widget.deck.info.title,
              leading: const BackNavButton(),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Align(
                alignment: Alignment.centerLeft,
                child: UiText(
                    images.isEmpty
                        ? '這 ${_deck.wordCount} 個字在詞庫裡還沒有圖片，可以先看單字'
                        : '單字集 · ${_deck.wordCount} 個單字 · ${images.length} 張詞庫圖片',
                    style: MFont.manrope(13, FontWeight.w600, MColors.muted)),
              ),
            ),
            Expanded(
              // 問題回報 #673: a page with no pictures still shows the words
              // (the C2 slice of 基礎 3000 字 is 4 abstract words).
              child: images.isEmpty
                  ? _WordList(deck: _deck)
                  : GridView.builder(
                      padding: const EdgeInsets.fromLTRB(
                          MSpace.md, 0, MSpace.md, MSpace.md),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        mainAxisSpacing: MSpace.sm,
                        crossAxisSpacing: MSpace.sm,
                        mainAxisExtent: 260,
                      ),
                      itemCount: images.length,
                      itemBuilder: (context, i) =>
                          DatabaseImageTile(image: images[i]),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A downloaded 單字集 on the 相片冊 grid (問題回報 #663).
class WordDeckAlbumCard extends StatelessWidget {
  final InstalledDeck deck;
  final VoidCallback onTap;

  const WordDeckAlbumCard({super.key, required this.deck, required this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: '${deck.info.title}，${deck.wordCount} 個單字',
        child: Container(
          decoration: BoxDecoration(
            color: MColors.primarySoft,
            borderRadius: MRadii.rLg,
            boxShadow: MShadows.card,
          ),
          padding: const EdgeInsets.all(MSpace.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: MSpace.xs, vertical: 2),
                decoration: MDecor.softPanel(color: Colors.white, radius: 10),
                child: UiText('單字集',
                    style: MFont.inter(11, FontWeight.w700, MColors.primary)),
              ),
              const Spacer(),
              const Icon(Icons.menu_book_rounded,
                  size: 36, color: MColors.primary),
              const SizedBox(height: MSpace.sm),
              Text(deck.info.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: MFont.inter(15, FontWeight.w700, MColors.ink)),
              const SizedBox(height: 2),
              UiText('${deck.wordCount} 個單字',
                  style: MFont.inter(12, FontWeight.w600, MColors.muted)),
            ],
          ),
        ),
      );
}

/// The words of a deck with no lexicon pictures: each opens 單字詳情.
class _WordList extends StatelessWidget {
  final InstalledDeck deck;

  const _WordList({required this.deck});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final entries = [
      for (final id in deck.entryIds(repo))
        if (repo.entry(id) case final e?) e
    ]..sort((a, b) => a.word.compareTo(b.word));
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(MSpace.md, 0, MSpace.md, MSpace.md),
      itemCount: entries.length,
      separatorBuilder: (_, __) => const SizedBox(height: MSpace.xs),
      itemBuilder: (context, i) {
        final e = entries[i];
        return Material(
          color: MColors.surface,
          borderRadius: MRadii.rLg,
          child: ListTile(
            key: ValueKey('deck-word-${e.word}'),
            title: Text(e.word,
                style: MFont.manrope(16, FontWeight.w800, MColors.ink)),
            subtitle: e.meaning.trim().isEmpty ? null : Text(e.meaning),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => scope.navigator.openWord(e.id),
          ),
        );
      },
    );
  }
}
