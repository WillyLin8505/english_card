part of '../screens/flashcard_screen.dart';

class _Intro extends StatelessWidget {
  final VoidCallback onStart;

  const _Intro({required this.onStart});

  @override
  Widget build(BuildContext context) {
    final repo = AppScope.of(context).repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final probe = FlashcardSession(repo, continuous: true);
        final any = !probe.finished;
        probe.dispose();
        final waiting = repo.hasCardsWaitingForMeaning;
        return Padding(
          padding: const EdgeInsets.all(MSpace.xl),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                    color: MColors.primarySoft,
                    shape: BoxShape.circle,
                    boxShadow: MShadows.soft,
                    border: Border.all(
                        color: MColors.primary.withValues(alpha: 0.12))),
                child:
                    const Center(child: MSvg(MIcon.tabCardsActive, size: 40)),
              ),
              const SizedBox(height: 20),
              UiText(
                  any
                      ? '想複習的時候就開始吧'
                      : waiting
                          ? '等待詞庫補齊'
                          : '還沒有可以複習的卡片',
                  style: MFont.manrope(20, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 8),
              UiText(
                // No due count (spec: 不顯示欠卡數).
                any
                    ? '不限張數，會持續出題。想休息時，按左上角結束。'
                    : waiting
                        ? '單字的中文意思補齊後，會自動加入複習。'
                        : '在照片詳情挑幾個單字，或從資料庫加入單字，就會變成卡片。',
                textAlign: TextAlign.center,
                style: MFont.manrope(14, FontWeight.w600, MColors.muted),
              ),
              const SizedBox(height: 28),
              if (any)
                PrimaryButton(label: '開始複習', onTap: onStart)
              else ...[
                PrimaryButton(
                  label: '去拍照選單字',
                  onTap: () =>
                      AppScope.of(context).navigator.selectTab(AppTab.camera),
                ),
                const SizedBox(height: 10),
                OutlinedButton(
                  onPressed: () =>
                      AppScope.of(context).navigator.selectTab(AppTab.album),
                  child: const UiText('查看相片冊'),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// The end of a run (spec §7's deferred 測驗結束畫面, card #217): how many
/// cards were graded this time, and nothing that nags — no streak, no due
/// or overdue count, no score (spec section 1: 不做連勝、欠卡壓力或罪惡感設計).
/// With nothing graded it only says the run is over.
class _Finished extends StatelessWidget {
  final int reviewed;
  final VoidCallback onDone;

  const _Finished({required this.reviewed, required this.onDone});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(MSpace.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (reviewed > 0)
              Container(
                width: 88,
                height: 88,
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                    color: MColors.primarySoft,
                    shape: BoxShape.circle,
                    boxShadow: MShadows.soft,
                    border: Border.all(
                        color: MColors.primary.withValues(alpha: 0.12))),
                child: const Center(
                    child: Icon(Icons.check_rounded,
                        size: 40, color: MColors.primary)),
              ),
            UiText(reviewed > 0 ? '這次複習了 $reviewed 張卡' : '目前沒有可作答的卡片',
                style: MFont.manrope(22, FontWeight.w800, MColors.ink)),
            const SizedBox(height: 8),
            UiText(
              reviewed > 0
                  ? '辛苦了。每張卡下次出現的時間已經排好，\n想複習時，再回來就好。'
                  : '這次的練習先到這裡。\n想複習時，再回來就好。',
              textAlign: TextAlign.center,
              style: MFont.manrope(14, FontWeight.w600, MColors.muted),
            ),
            const SizedBox(height: 28),
            PrimaryButton(label: '完成', onTap: onDone),
          ],
        ),
      );
}

/// The card under review (front or back) and the fixed bottom bar.
class FlashcardCardView extends StatelessWidget {
  final FlashcardSession session;

  const FlashcardCardView({super.key, required this.session});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    session.guardPhoto();
    final repo = scope.repository;
    final card = session.card!;
    final entry = repo.entry(card.wordEntryId);
    if (entry == null) return const SizedBox.shrink();
    // The usage/sense actually tested this round, so the back shows the
    // same part of speech and meaning as the exercise, not the entry's
    // default usage (問題回報 #4).
    LexemeUsage? activeUsage;
    for (final u in entry.effectiveUsages) {
      if (u.id == session.usageId) {
        activeUsage = u;
        break;
      }
    }
    WordSense? activeSense;
    if (activeUsage != null) {
      for (final s in activeUsage.senses) {
        if (s.id == session.senseId) {
          activeSense = s;
          break;
        }
      }
    }
    final native = scope.settings.nativeLanguage;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final look = CardLook.of(context);
    return Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
            child: _CardFrame(
                look: look,
                child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              child: session.showingBack
                  ? FlashcardBack(
                      key: ValueKey('back:${card.id}'),
                      entry: entry,
                      activePos: activeUsage?.pos,
                      activeMeaning: activeSense?.meaning,
                      activeDefinition: activeSense?.definition,
                      card: card,
                      photo: session.photo,
                      anchor: session.anchor,
                      photoCredit: session.photoCredit,
                      photos: session.photoOptions,
                      onPhotoSelected: session.selectPhoto,
                      answerCorrect: session.answerCorrect,
                      submittedAnswer: session.submittedAnswer,
                      correctAnswer: session.exercise?.answer,
                      template: repo.template,
                      learnerLevel: repo.profile.cefr,
                      onPlay: () => scope.speak(context, entry.word,
                          language: repo.language, audioUrl: entry.audioUrl),
                      onOpen: () => scope.navigator.openWord(entry.id),
                    )
                  : FlashcardFront(
                      key: ValueKey('front:${card.id}'),
                      entry: entry,
                      session: session),
            )),
          ),
        ),
        // Fixed at the bottom (spec: 畫面底部固定「顯示答案」／四個評分按鈕).
        Container(
          padding: EdgeInsets.fromLTRB(
              MSpace.lg, MSpace.sm, MSpace.lg, MSpace.md + bottom),
          decoration: look.dock,
          child: session.showingBack
              ? RatingBar(
                  previews: session.ratingPreviews,
                  native: native,
                  extraPractice: session.isExtraPractice,
                  onRate: session.rate,
                )
              : PrimaryButton(
                  label: '顯示答案',
                  decoration: look.answerButton,
                  height: look.answerHeight,
                  textStyle: look.answerText,
                  shortcut:
                      session.exercise?.type == ReviewExerciseType.photoRecall
                          ? '空白鍵'
                          : null,
                  onTap: !session.canAnswer
                      ? null
                      : () {
                          if (session.exercise?.type !=
                              ReviewExerciseType.photoRecall) {
                            session.useHint();
                          }
                          session.showAnswer();
                        }),
        ),
      ],
    );
  }
}


/// The card around the front and the back, in the chosen 卡片樣式
/// (問題回報 #317); the classic style has none.
class _CardFrame extends StatelessWidget {
  final CardLook look;
  final Widget child;

  const _CardFrame({required this.look, required this.child});

  @override
  Widget build(BuildContext context) {
    final card = look.card;
    final accent = look.buttonAccent;
    var framed = child;
    if (accent != null) {
      framed = Theme(
        data: Theme.of(context).copyWith(
          outlinedButtonTheme: OutlinedButtonThemeData(
            style: OutlinedButton.styleFrom(
              foregroundColor: accent,
              minimumSize: const Size(0, 48),
              side: BorderSide(color: accent, width: 1.5),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(look.buttonRadius)),
              textStyle: MFont.manrope(15, FontWeight.w800, accent),
            ),
          ),
        ),
        child: framed,
      );
    }
    if (card == null) return framed;
    return Container(
        key: const ValueKey('card-frame'),
        decoration: card,
        padding: look.cardPadding,
        child: framed);
  }
}

/// A back-of-card section. Longer sections (spec section 5: 較長的相關字、
/// 詞源與來源區塊可預設收合) start [collapsed]; tapping the title opens them.
