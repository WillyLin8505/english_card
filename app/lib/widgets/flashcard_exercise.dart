part of '../screens/flashcard_screen.dart';

class _InteractiveExercise extends StatefulWidget {
  final FlashcardSession session;
  final WordEntry entry;

  const _InteractiveExercise({required this.session, required this.entry});

  @override
  State<_InteractiveExercise> createState() => _InteractiveExerciseState();
}

class _InteractiveExerciseState extends State<_InteractiveExercise> {
  final _answer = TextEditingController();
  String? _meaning;
  late List<ExercisePair> _pairs;
  final _matched = <String>{};
  final _placed = <String>{};
  var _attempts = 0;
  var _mistakes = 0;

  @override
  void initState() {
    super.initState();
    _pairs = [...widget.session.exercise!.pairs]
      ..shuffle(math.Random(widget.session.card!.id.hashCode));
  }

  @override
  void dispose() {
    _answer.dispose();
    super.dispose();
  }

  /// The exercise photo. With [mark], the word's spot is ringed (spec
  /// section 7: 正面「照片與目標區域」; 卡 #253) — a ring, and the tagger's
  /// box when it has one, but no word: the front must not give it away.
  /// A photo without the word's coordinates shows no mark. The drag
  /// question passes its own [height], [fit] and [overlay] (its drop spots).
  ///
  /// With [dot] (and no [mark]) the word's spot gets the card back's blue
  /// dot instead (問題回報 #849 複習：正面也要呈現藍點) — the dot only, never
  /// the word's label, so the front does not give the answer away. A word
  /// with no spot on this photo (unplaced, 整張圖, no point) has no dot.
  Widget _photo(
      {bool mark = true,
      bool dot = false,
      double? height,
      BoxFit? fit,
      Widget? overlay}) {
    final s = widget.session;
    final photo = s.photo;
    if (photo == null) return const SizedBox.shrink();
    final attempt = s.photoAttempt;
    final anchor = s.anchor;
    final look = CardLook.of(context);
    return SizedBox(
      height: height ?? look.frontPhotoHeight,
      child: Stack(fit: StackFit.expand, children: [
        PinnedPhoto(
          key: ValueKey(attempt),
          photo: photo,
          radius: look.frontPhotoRadius,
          pins: const [],
          fit: fit ?? BoxFit.cover,
          // 問題回報 #651: the word's spot stays in the frame, even when
          // BoxFit.cover would crop it away (the ring then follows).
          focus: anchor,
          overlay: overlay ??
              (mark && anchor != null && !s.photoFailed
                  ? Semantics(
                      label: ui(context, '照片中標出的位置'),
                      child:
                          TargetRing(photo: photo, anchor: anchor, box: s.box))
                  : dot && anchor != null && !s.photoFailed
                      ? Semantics(
                          label: ui(context, '照片中標出的位置'),
                          child: _AnchorDot(
                              photo: photo,
                              anchor: anchor,
                              dotKey: const ValueKey('front-anchor-dot')))
                      : null),
          onImageState: (ready) => s.reportPhotoState(attempt, ready),
          imageErrorBuilder: (_) => const Center(child: UiText('圖片暫時無法載入')),
        ),
        if (s.photoFailed)
          Align(
              alignment: Alignment.bottomCenter,
              child: OutlinedButton(
                  onPressed: s.retryPhoto, child: const UiText('重試圖片')))
        else if (!s.canAnswer)
          const Align(
              alignment: Alignment.bottomCenter, child: UiText('正在載入圖片…')),
      ]),
    );
  }

  Widget _title(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: UiText(text,
            textAlign: TextAlign.center,
            style: CardLook.of(context).exerciseTitle),
      );

  @override
  Widget build(BuildContext context) {
    final x = widget.session.exercise!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (x.type == ReviewExerciseType.sentenceCloze) ...[
          // Card #561 (issue #609): the fill-in front shows the word's photo
          // too, so the sentence and the picture work together. No ring, but
          // the back's blue dot on the word's spot (問題回報 #849): it says
          // where to look, not what the word is.
          if (widget.session.photo != null) ...[
            _photo(mark: false, dot: true),
            const SizedBox(height: 18),
          ],
          _title(x.prompt),
          if (x.translation != null)
            Text(x.translation!,
                textAlign: TextAlign.center,
                style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
          const SizedBox(height: 18),
          TextField(
            controller: _answer,
            textAlign: TextAlign.center,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _submitText(),
            decoration: InputDecoration(
              suffixIcon: IconButton(
                tooltip: ui(context, '送出答案'),
                onPressed: _submitText,
                icon: const Icon(Icons.arrow_forward),
              ),
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              tooltip: ui(context,
                  widget.session.hintCount > 0 ? '提示已顯示' : '顯示字首提示'),
              onPressed: !widget.session.canAnswer ||
                      widget.session.hintCount > 0
                  ? null
                  : () {
                      widget.session.useHint();
                      setState(() {});
                    },
              icon: const Icon(Icons.lightbulb_outline),
            ),
          ),
          if (widget.session.hintCount > 0)
            Text(firstLetterHint(x.answer), textAlign: TextAlign.center),
        ],
        if (x.type == ReviewExerciseType.photoChoice) ...[
          // 問題回報 #697: 選單字題 shows the photo without the target ring —
          // the ring sat on top of the tagger's box, two marks in one spot,
          // and the question is about the whole photo.
          // 問題回報 #849: the back's small blue dot marks the word's spot
          // instead (no box, no word), like the card back draws it.
          _photo(mark: false, dot: true),
          const SizedBox(height: 18),
          _title(x.prompt),
          for (final option in x.options)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: OutlinedButton(
                  onPressed: widget.session.canAnswer
                      ? () => widget.session.submitAnswer(option)
                      : null,
                  child: Text(shownWord(option, AppScope.of(context).repository.language))),
            ),
        ],
        if (x.type == ReviewExerciseType.similarMatch) ...[
          _title(x.prompt),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              for (final pair in _pairs)
                ChoiceChip(
                  label: Text(pair.meaning),
                  selected: _meaning == pair.meaning,
                  onSelected: _matched.contains(pair.word)
                      ? null
                      : (_) => setState(() => _meaning = pair.meaning),
                ),
            ],
          ),
          const SizedBox(height: 18),
          for (final pair in x.pairs)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: OutlinedButton(
                onPressed: _matched.contains(pair.word) || _meaning == null
                    ? null
                    : () => _match(pair),
                child: Text(_matched.contains(pair.word)
                    ? '✓ ${shownWord(pair.word, AppScope.of(context).repository.language)}'
                    : shownWord(pair.word, AppScope.of(context).repository.language)),
              ),
            ),
          if (_mistakes > 0)
            UiText('這一組不相符，再試一次。',
                textAlign: TextAlign.center,
                style: MFont.manrope(13, FontWeight.w700, Colors.red)),
        ],
        if (x.type == ReviewExerciseType.photoRecall) ...[
          // 問題回報 #849: the target ring (卡 #253) already marks the spot,
          // with the focal dot at its centre — no second dot.
          _photo(),
          const SizedBox(height: 18),
          _title(x.prompt),
          // The part of speech is UI copy (名詞 → Noun for an English
          // speaker), not dictionary text (卡 #496 round 5).
          if (x.translation != null)
            Text(ui(context, x.translation!),
                textAlign: TextAlign.center,
                style: MFont.manrope(14, FontWeight.w700, MColors.label)),
          const SizedBox(height: 12),
          OutlinedButton(
              onPressed: !widget.session.canAnswer ||
                      widget.session.hintCount > 0
                  ? null
                  : () {
                      widget.session.useHint();
                      setState(() {});
                    },
              child: UiText(widget.session.hintCount == 0
                  ? '需要提示'
                  : '提示已顯示')),
          if (widget.session.hintCount > 0)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(firstLetterHint(x.answer),
                  textAlign: TextAlign.center),
            ),
        ],
        if (x.type == ReviewExerciseType.imageDrag) ...[
          _title(x.prompt),
          _dragPhoto(x),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              for (final target in x.targets)
                if (!_placed.contains(target.word))
                  Draggable<String>(
                    maxSimultaneousDrags: widget.session.canAnswer ? 1 : 0,
                    data: target.word,
                    feedback: Material(
                        color: Colors.transparent,
                        child:
                            TagChip(shownWord(target.word, AppScope.of(context).repository.language), localize: false)),
                    childWhenDragging: Opacity(
                        opacity: .25,
                        child:
                            TagChip(shownWord(target.word, AppScope.of(context).repository.language), localize: false)),
                    child: TagChip(shownWord(target.word, AppScope.of(context).repository.language), localize: false),
                  ),
            ],
          ),
          if (_mistakes > 0) ...[
            const SizedBox(height: 10),
            UiText('位置不正確，詞籤已回到原位，請再試一次。',
                textAlign: TextAlign.center,
                style: MFont.manrope(13, FontWeight.w700, MColors.againFg)),
          ],
        ],
      ],
    );
  }

  void _submitText() {
    if (_answer.text.trim().isNotEmpty) {
      widget.session.submitAnswer(_answer.text);
    }
  }

  void _match(ExercisePair word) {
    _attempts++;
    final correct = word.meaning == _meaning;
    setState(() {
      if (correct) {
        _matched.add(word.word);
        _meaning = null;
      } else {
        _mistakes++;
      }
    });
    if (_matched.length == widget.session.exercise!.pairs.length) {
      widget.session
          .completeInteraction(correct: _mistakes == 0, attempts: _attempts);
    }
  }

  /// 問題回報 #696: the drop spots are mapped through the photo's own
  /// geometry ([CoverGeometry]), as the labels are. Before, they were put
  /// at anchor × frame size in a fixed 4:3 frame while the photo was
  /// cropped (cover) and shifted (focus), so a spot drifted off its object
  /// — and any label in the cropped strip was off the photo. Now the frame
  /// takes the photo's shape and shows all of it.
  Widget _dragPhoto(ReviewExercise x) => LayoutBuilder(builder: (context, c) {
        final photo = widget.session.photo;
        final frame = photo == null
            ? Size(c.maxWidth, c.maxWidth * 3 / 4)
            : dragPhotoFrame(photo, c.maxWidth);
        // 問題回報 #849: no blue dot here — the learner drags the word to
        // its spot, so a dot would point at the answer (the drop spots are
        // the only marks).
        return _photo(
          mark: false,
          height: frame.height,
          fit: BoxFit.contain,
          overlay: photo == null || !widget.session.canAnswer
              ? null
              : LayoutBuilder(builder: (context, box) {
                  final geo = CoverGeometry.of(
                      context, Size(box.maxWidth, box.maxHeight), photo);
                  return Stack(children: [
                    for (final target in x.targets)
                      if (geo.toBox(target.anchor) case final at)
                        Positioned(
                          key: ValueKey('drop-${target.word}'),
                          left: at.dx - 28,
                          top: at.dy - 28,
                          width: 56,
                          height: 56,
                          child: _dropSpot(x, target),
                        ),
                  ]);
                }),
        );
      });

  Widget _dropSpot(ReviewExercise x, ExerciseTarget target) =>
      DragTarget<String>(
        onAcceptWithDetails: (details) {
          if (!widget.session.canAnswer) return;
          _attempts++;
          if (details.data == target.word) {
            setState(() => _placed.add(target.word));
            if (_placed.length == x.targets.length) {
              widget.session.completeInteraction(
                  correct: _mistakes == 0, attempts: _attempts);
            }
          } else {
            setState(() => _mistakes++);
          }
        },
        builder: (_, candidate, __) => Container(
          decoration: BoxDecoration(
            color: _placed.contains(target.word)
                ? MColors.primary.withValues(alpha: .85)
                : MColors.surface.withValues(alpha: .75),
            shape: BoxShape.circle,
            border: Border.all(color: MColors.primary, width: 2),
          ),
          child: Center(
              child: Text(_placed.contains(target.word) ? '✓' : '＋',
                  style: MFont.manrope(20, FontWeight.w800, MColors.ink))),
        ),
      );
}

/// The drag question's photo frame [width] wide: the photo's own shape
/// (all of it shown), no taller than square; 4:3 for a photo of unknown
/// size. The review screen preloads the photo at this size too.
Size dragPhotoFrame(Photo photo, double width) => Size(
    width,
    PinnedPhoto.frameHeight(photo, width,
        maxHeight: width, minHeight: 160, fallback: width * 3 / 4));
