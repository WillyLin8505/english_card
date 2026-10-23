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
  /// A photo without the word's coordinates shows no mark.
  Widget _photo({bool mark = true}) {
    final s = widget.session;
    final photo = s.photo;
    if (photo == null) return const SizedBox.shrink();
    final attempt = s.photoAttempt;
    final anchor = s.anchor;
    final look = CardLook.of(context);
    return SizedBox(
      height: look.frontPhotoHeight,
      child: Stack(fit: StackFit.expand, children: [
        PinnedPhoto(
          key: ValueKey(attempt),
          photo: photo,
          radius: look.frontPhotoRadius,
          pins: const [],
          // 問題回報 #651: the word's spot stays in the frame, even when
          // BoxFit.cover would crop it away (the ring then follows).
          focus: anchor,
          overlay: mark && anchor != null && !s.photoFailed
              ? Semantics(
                  label: ui(context, '照片中標出的位置'),
                  child: TargetRing(photo: photo, anchor: anchor, box: s.box))
              : null,
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
          // too, unmarked, so the sentence and the picture work together.
          if (widget.session.photo != null) ...[
            _photo(mark: false),
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
          _photo(),
          const SizedBox(height: 18),
          _title(x.prompt),
          for (final option in x.options)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: OutlinedButton(
                  onPressed: widget.session.canAnswer
                      ? () => widget.session.submitAnswer(option)
                      : null,
                  child: Text(displayWord(option))),
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
                    ? '✓ ${displayWord(pair.word)}'
                    : displayWord(pair.word)),
              ),
            ),
          if (_mistakes > 0)
            UiText('這一組不相符，再試一次。',
                textAlign: TextAlign.center,
                style: MFont.manrope(13, FontWeight.w700, Colors.red)),
        ],
        if (x.type == ReviewExerciseType.photoRecall) ...[
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
                            TagChip(displayWord(target.word), localize: false)),
                    childWhenDragging: Opacity(
                        opacity: .25,
                        child:
                            TagChip(displayWord(target.word), localize: false)),
                    child: TagChip(displayWord(target.word), localize: false),
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

  Widget _dragPhoto(ReviewExercise x) => AspectRatio(
        aspectRatio: 4 / 3,
        child: LayoutBuilder(builder: (context, box) {
          return Stack(children: [
            Positioned.fill(child: _photo(mark: false)),
            for (final target
                in widget.session.canAnswer ? x.targets : <ExerciseTarget>[])
              Positioned(
                left: target.anchor.x * box.maxWidth - 28,
                top: target.anchor.y * box.maxHeight - 28,
                width: 56,
                height: 56,
                child: DragTarget<String>(
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
                            style: MFont.manrope(
                                20, FontWeight.w800, MColors.ink))),
                  ),
                ),
              ),
          ]);
        }),
      );
}

/// Back (spec sections 4 and 7): the answer, its pronunciation (played on
/// flip), meaning, one of the word's photos, 3–5 examples, then the
/// card template's other fields in its order; empty fields are left out.
/// 所有資訊 opens the full word.
