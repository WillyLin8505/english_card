/// Traditional Chinese source keys are stable UI identifiers, never dictionary
/// content. Missing keys/languages deliberately retain the original copy.
const uiCatalog = <String, (String, String)>{
  '意見回饋': ('Feedback', 'Commentaires'),
  // 問題回報 #558: the card back's folded definition (A1–B1).
  '顯示定義': ('Show definition', 'Afficher la définition'),
  '收起定義': ('Hide definition', 'Masquer la définition'),
  // M180 (owner #732): the photo's 詞性 × CEFR table.
  '詞性 × 等級表': ('Part of speech × level', 'Nature × niveau'),
  '加入單字本': ('Add to My words', 'Ajouter à Mes mots'),
  // 卡 #496 (M156–M162, 問題回報 #494): copy a French learner on an English
  // or French phone still saw in Chinese.
  '重新掃描標籤': ('Rescan labels', 'Réanalyser les étiquettes'),
  '自己加字': ('Add a word', 'Ajouter un mot'),
  '放到照片上': ('Place on the photo', 'Placer sur la photo'),
  '不放位置': ('No position', 'Sans position'),
  '左滑單字表示已經會了；拖曳照片上的標籤可調整位置；點標籤可改字或刪除。': (
    'Swipe a word left if you know it; drag a label on the photo to move it; tap a label to change or delete it.',
    'Balayez un mot vers la gauche si vous le connaissez ; faites glisser une étiquette pour la déplacer ; touchez-la pour la modifier ou la supprimer.'
  ),
  '可查看意思、改成正確的字、刪除或標為已學會。': (
    'See the meaning, correct the word, delete it or mark it as learned.',
    'Voir le sens, corriger le mot, le supprimer ou le marquer comme appris.'
  ),
  '刪除（照片裡沒有這個）': (
    'Delete (not in the photo)',
    'Supprimer (absent de la photo)'
  ),
  '中文可以留空，會用詞庫的意思。': (
    'The meaning can stay empty; the dictionary’s is used.',
    'Le sens peut rester vide ; celui du dictionnaire est utilisé.'
  ),
  '改了英文、中文沒改，會改用詞庫的意思。': (
    'If you change the word but not the meaning, the dictionary’s meaning is used.',
    'Si vous changez le mot sans le sens, le sens du dictionnaire est utilisé.'
  ),
  '送出': ('Send', 'Envoyer'),
  '回報此卡片': ('Report this card', 'Signaler cette carte'),
  '會一併附上這張卡的單字、詞性、義項、照片與 App 版本。': (
    'The card’s word, part of speech, sense, photo and app version are attached.',
    'Le mot, la nature, le sens, la photo de la carte et la version de l’app sont joints.'
  ),
  '這張卡片會從複習移除，並加入「已學會」。之後可以在單字本裡復原。': (
    'This card leaves your reviews and goes to “Learned”. You can restore it from My words.',
    'Cette carte quitte vos révisions et passe dans « Appris ». Vous pouvez la restaurer depuis Mes mots.'
  ),
  '超過的新卡順延到明天。預設 20 張。': (
    'Extra new cards move to tomorrow. Default: 20.',
    'Les nouvelles cartes en trop passent à demain. Par défaut : 20.'
  ),
  '超過的複習順延到明天。預設 100 張。': (
    'Extra reviews move to tomorrow. Default: 100.',
    'Les révisions en trop passent à demain. Par défaut : 100.'
  ),
  '掃描 QR code': ('Scan QR code', 'Scanner le QR code'),
  '掃描連線 QR code': ('Scan the connection QR code', 'Scanner le QR code de connexion'),
  '還原會用備份檔取代目前所有的單字、照片、相片冊、複習紀錄與設定。': (
    'Restoring replaces all your words, photos, albums, review history and settings with the backup.',
    'La restauration remplace tous vos mots, photos, albums, historique de révision et réglages par la sauvegarde.'
  ),
  '下載相片冊': ('Download album', 'Télécharger l’album'),
  '已在相片冊': ('Already in your albums', 'Déjà dans vos albums'),
  '開啟相簿': ('Open album', 'Ouvrir l’album'),
  '複習這本相簿': ('Review this album', 'Réviser cet album'),
  '標籤': ('Labels', 'Étiquettes'),
  '圖片來源': ('Picture sources', 'Sources des images'),
  '圖片來源：維基共享資源': (
    'Picture source: Wikimedia Commons',
    'Source de l’image : Wikimedia Commons'
  ),
  '照片中標出的位置': ('The spot marked in the photo', 'L’endroit marqué sur la photo'),
  '這個詞性顯示同拼法名詞的圖片。這個拼法沒有名詞。': (
    'This part of speech shows pictures of the noun with the same spelling. This spelling has no noun.',
    'Cette nature affiche les images du nom de même orthographe. Cette orthographe n’a pas de nom.'
  ),
  '新增相關字': ('Add a related word', 'Ajouter un mot associé'),
  '刪除相關字': ('Delete related word', 'Supprimer le mot associé'),
  '新增詞形變化': ('Add a form', 'Ajouter une forme'),
  '刪除詞形變化': ('Delete form', 'Supprimer la forme'),
  '可直接修改內容；清空構詞或詞源即可刪除。': (
    'Edit directly; clear word parts or etymology to delete them.',
    'Modifiez directement ; videz la formation ou l’étymologie pour les supprimer.'
  ),
  '授權條文': ('License texts', 'Textes des licences'),
  '圖片在 App 內以縮小後的縮圖顯示，未做其他修改。': (
    'Pictures appear in the app as reduced thumbnails, with no other changes.',
    'Les images apparaissent dans l’app en miniatures réduites, sans autre modification.'
  ),
  // 設定 → 我的意見回饋 (問題回報 #701).
  '我的意見回饋': ('My feedback', 'Mes commentaires'),
  '看這支手機送過的意見回饋與卡片回報，也可以刪除。': (
    'See the feedback and card reports sent from this phone, and delete them.',
    'Voir les commentaires et signalements envoyés depuis ce téléphone, et les supprimer.'
  ),
  // 問題回報 #716 / #728: deleting a sent one deletes its 問題回報 too; each
  // shows whether it is being handled or done.
  '這支手機送過的意見回饋與卡片回報，以及處理進度。刪除已送出的會連問題回報一起刪除；還沒送出的就不會送出。': (
    'Feedback and card reports sent from this phone, and their progress. Deleting a sent one also deletes the report; unsent ones won’t be sent.',
    'Commentaires et signalements envoyés depuis ce téléphone, et leur suivi. Supprimer un envoi supprime aussi le signalement ; ceux non envoyés ne le seront pas.'
  ),
  '會從這支手機和問題回報一起刪除。': (
    'It will be deleted from this phone and from the reports.',
    'Il sera supprimé de ce téléphone et des signalements.'
  ),
  '沒辦法從問題回報刪除': (
    'Couldn’t delete the report',
    'Impossible de supprimer le signalement'
  ),
  '伺服器沒有刪掉這筆回報，紀錄先留在這支手機。可以稍後再試。': (
    'The server didn’t delete this report, so it stays on this phone. You can try again later.',
    'Le serveur n’a pas supprimé ce signalement ; il reste sur ce téléphone. Vous pouvez réessayer plus tard.'
  ),
  '只從這支手機移除': ('Remove from this phone only', 'Retirer de ce téléphone seulement'),
  '先留著': ('Keep it', 'Le garder'),
  '還沒有送過意見回饋': ('No feedback sent yet', 'Aucun commentaire envoyé'),
  '還在排隊，連上網路後會送出': (
    'Waiting; sent once you’re online',
    'En attente ; envoyé dès la connexion'
  ),
  '已送出': ('Sent', 'Envoyé'),
  '刪除': ('Delete', 'Supprimer'),
  '刪除這筆紀錄？': ('Delete this entry?', 'Supprimer cette entrée ?'),
  '還沒送出的會取消，不會再送出。': (
    'It hasn’t been sent yet and won’t be.',
    'Il n’a pas encore été envoyé et ne le sera pas.'
  ),
  '只會從這支手機移除，已送到問題回報的不會刪除。': (
    'Removed from this phone only; the report already sent stays.',
    'Retiré de ce téléphone seulement ; le signalement déjà envoyé reste.'
  ),
  '你的答案': ('Yours', 'Votre réponse'),
  '正確答案': ('Answer', 'Réponse'),
  '詞庫還沒有這個單字集的圖片': (
    'No lexicon pictures for this word set yet',
    'Pas encore d’images pour cette liste de mots'
  ),
  '附上這個畫面的截圖': (
    'Attach a screenshot of this screen',
    'Joindre une capture de cet écran'
  ),
  '這一本現在沒有可以複習的卡，單字的{N}意思補齊後會自動加入': (
    'Nothing to review in this one yet; words join once their {N} meaning is in',
    'Rien à réviser ici pour l’instant ; les mots arrivent dès que leur sens en {N} est prêt'
  ),
  '這一本現在沒有可以複習的卡': (
    'Nothing to review in this one yet',
    'Rien à réviser ici pour l’instant'
  ),
  // 問題回報 #641.
  '上一張卡片': ('Previous card', 'Carte précédente'),
  '回到正面': ('Back to front', 'Revoir le recto'),
  '回到這張卡片': ('Back to this card', 'Revenir à cette carte'),
  '這是上一張卡片，已經評分過': (
    'This is the previous card; it is already graded',
    'C’est la carte précédente ; elle est déjà notée'
  ),
  // 長按辨識 (問題回報 #616).
  'AI 在這裡看到': ('The AI sees here', 'L’IA voit ici'),
  'AI 在這裡沒有認出東西': ('The AI found nothing here', 'L’IA n’a rien reconnu ici'),
  '可以換個位置再長按，或自己輸入。': (
    'Long-press another spot, or type the word yourself.',
    'Appuyez longuement ailleurs, ou saisissez le mot vous-même.'
  ),
  '選一個字，就會在你長按的位置加上標籤。': (
    'Pick a word to label the spot you pressed.',
    'Choisissez un mot pour étiqueter l’endroit touché.'
  ),
  '已在照片上，選它會移到這裡': (
    'Already on the photo; picking it moves it here',
    'Déjà sur la photo ; le choisir le déplace ici'
  ),
  '移到這裡': ('Move here', 'Déplacer ici'),
  '都不是，自己輸入': ('None of these, type it', 'Aucun, saisir le mot'),
  '或在照片上長按，讓 AI 認那個位置': (
    'or long-press the photo to have the AI read that spot',
    'ou appuyez longuement sur la photo pour que l’IA lise cet endroit'
  ),
  '還沒設定照片辨識：到 設定 → 進階設定 → 照片辨識連線': (
    'Photo recognition isn’t set up: Settings → Advanced → Photo recognition',
    'Reconnaissance non configurée : Réglages → Avancé → Reconnaissance des photos'
  ),
  '辨識失敗，請檢查網路後再試': (
    'Recognition failed; check your connection and try again',
    'Échec de la reconnaissance ; vérifiez la connexion et réessayez'
  ),
  '已送出，謝謝你的意見': ('Sent, thank you', 'Envoyé, merci'),
  '會一併附上目前頁面、App 版本與學習語言。': (
    'The current page, app version and learning language are attached.',
    'La page, la version de l’app et la langue apprise sont jointes.'
  ),
  '卡片集': ('Decks', 'Paquets'),
  '瀏覽並下載卡片集': (
    'Browse and download decks',
    'Parcourir et télécharger des paquets'
  ),
  '卡片集：下載別人整理好的單字集與圖片集': (
    'Decks: download word and picture sets made by others',
    'Paquets : télécharger des listes de mots et d’images'
  ),
  '目前還沒有卡片集': ('No decks yet', 'Aucun paquet pour le moment'),
  '加入': ('Add', 'Ajouter'),
  '移除': ('Remove', 'Retirer'),
  '集合裡的圖片與單字會從你的收藏移除；已經複習過或你編輯過的單字會保留。': (
    'The deck’s pictures and words are removed from your collection; words you reviewed or edited are kept.',
    'Les images et mots du paquet sont retirés de votre collection ; les mots révisés ou modifiés sont conservés.'
  ),
  '詞庫已更新': ('Dictionary updated', 'Dictionnaire mis à jour'),
  '知道了': ('Got it', 'Compris'),
  '關閉提示': ('Dismiss', 'Fermer'),
  '結束複習': ('End review', 'Terminer la révision'),
  '找不到這個單字': ('Word not found', 'Mot introuvable'),
  '編輯單字': ('Edit word', 'Modifier le mot'),
  '圖片與單字標籤': ('Photo and word labels', 'Photo et étiquettes'),
  '圖片標籤': ('Photo labels', 'Étiquettes de la photo'),
  '圖片資訊': ('Photo information', 'Informations sur la photo'),
  '點標籤查看{N}意思與例句。': (
    'Tap a label for its {N} meaning and examples.',
    'Touchez une étiquette pour voir son sens en {N} et les exemples.'
  ),
  '這張圖片已從資料庫移除': (
    'This photo was removed from the database',
    'Cette photo a été retirée du dictionnaire'
  ),
  '第一次學這張卡': ('First time learning this card', 'Première étude de cette carte'),
  '學習資訊': ('Learning information', 'Informations d’apprentissage'),
  '音標': ('Pronunciation', 'Prononciation'),
  '例句翻譯': ('Example translation', 'Traduction de l’exemple'),
  '相關字': ('Related words', 'Mots associés'),
  '構詞與詞源': ('Word formation and etymology', 'Formation et étymologie'),
  '來源': ('Source', 'Source'),
  '後台詞庫': ('Dictionary service', 'Service de dictionnaire'),
  '等級': ('Level', 'Niveau'),
  '自訂': ('Custom', 'Personnalisé'),
  '解釋': ('Explanation', 'Explication'),
  'AI 估計': ('AI estimate', 'Estimation IA'),
  '詞頻估計': ('Frequency estimate', 'Estimation de fréquence'),
  '很簡單': ('Very easy', 'Très facile'),
  '簡單': ('Easy', 'Facile'),
  '難': ('Hard', 'Difficile'),
  '剛好': ('At your level', 'À votre niveau'),
  '稍難': ('A little harder', 'Un peu plus difficile'),
  '挑戰': ('Challenging', 'Un défi'),
  '收起難度選單': ('Close difficulty menu', 'Fermer le menu de difficulté'),
  '放開手指完成': ('Release to finish', 'Relâchez pour terminer'),
  '顯示已學會單字': ('Show learned words', 'Afficher les mots acquis'),
  '已學會與學習中的舊詞': (
    'Previously learned and current words',
    'Mots déjà acquis et en cours'
  ),
  '返回時自動保存，不用再按建立。': (
    'Saved automatically when you go back; no Create button needed.',
    'Enregistré automatiquement en revenant en arrière ; pas de bouton Créer.'
  ),
  '左滑單字表示已經會了；拖曳照片上的標籤可調整位置。': (
    'Swipe a word left if you know it; drag photo labels to reposition them.',
    'Balayez un mot à gauche si vous le connaissez ; faites glisser les étiquettes pour les déplacer.'
  ),
  '打開「顯示已學會單字」可以看到照片裡已經學過的詞。': (
    'Turn on “Show learned words” to see familiar words in the photo.',
    'Activez « Afficher les mots acquis » pour voir les mots déjà appris sur la photo.'
  ),
  '這張照片沒有新的單字': (
    'No new words in this photo',
    'Aucun nouveau mot sur cette photo'
  ),
  '可以拖動難度條，或按「多看動詞」找找看其他的詞。': (
    'Drag the difficulty bar or tap “More verbs” to find other words.',
    'Faites glisser la barre de difficulté ou touchez « Plus de verbes » pour trouver d’autres mots.'
  ),
  'AI 先從照片找出候選詞，再由這台裝置依程度、未知機率、圖片關聯、實用性與詞性多樣性打分，最多選 5 個；名詞最多 3 個，同義詞只留一個。': (
    'AI proposes words from the photo. This device scores level, familiarity, relevance, usefulness and variety, choosing up to five words, at most three nouns, and one of each synonym group.',
    'L’IA propose des mots. Cet appareil évalue le niveau, la familiarité, la pertinence, l’utilité et la variété pour choisir au plus cinq mots, dont trois noms et un seul mot par groupe de synonymes.'
  ),
  '拖曳調整順序；關閉的欄位不會出現在卡片背面。{L}單字固定為標題。': (
    'Drag to reorder. Hidden fields are omitted from the back. The {L} word remains the title.',
    'Faites glisser pour réorganiser. Les champs masqués sont omis du verso. Le mot en {L} reste le titre.'
  ),
  '等待 AI 辨識': ('Waiting for AI recognition', 'En attente de reconnaissance IA'),
  'AI 辨識中…': ('AI recognition in progress…', 'Reconnaissance IA en cours…'),
  '跳過動畫': ('Skip animation', 'Passer l’animation'),
  'AI 辨識沒有成功': ('AI recognition failed', 'Échec de la reconnaissance IA'),
  'AI 服務恢復連線後會自動處理，不用一直等在這裡。': (
    'Processing resumes when AI reconnects. You can leave this page.',
    'Le traitement reprendra à la reconnexion de l’IA. Vous pouvez quitter cette page.'
  ),
  '前往設定': ('Go to settings', 'Ouvrir les réglages'),
  '這台裝置沒有照片辨識': (
    'This device cannot recognise photos',
    'Cet appareil ne peut pas reconnaître les photos'
  ),
  '這台裝置目前無法辨識照片，照片會先留在相片冊。': (
    'This device cannot recognise photos yet; the photo stays in the album.',
    'Cet appareil ne peut pas encore reconnaître les photos ; la photo reste dans l’album.'
  ),
  '照片辨識': ('Photo recognition', 'Reconnaissance photo'),
  '照片在這支手機上辨識，不會上傳到任何伺服器。': (
    'Photos are recognised on this phone and never uploaded to a server.',
    'Les photos sont reconnues sur ce téléphone et ne sont jamais envoyées à un serveur.'
  ),
  '這台裝置沒有本機照片辨識，照片會先留在相片冊。': (
    'This device has no on-device photo recognition; photos stay in the album.',
    'Cet appareil n’a pas de reconnaissance photo locale ; les photos restent dans l’album.'
  ),
  '尚未有可用相機或照片': (
    'No camera or photo available yet',
    'Aucun appareil photo ni photo disponible'
  ),
  '你可以按下方「選擇照片」，開始學單字。': (
    'Choose a photo below to start learning words.',
    'Choisissez une photo ci-dessous pour commencer.'
  ),
  '請稍後再試。': ('Please try again later.', 'Veuillez réessayer plus tard.'),
  '還沒有照片': ('No photos yet', 'Aucune photo pour le moment'),
  '找不到符合的照片': ('No matching photos', 'Aucune photo correspondante'),
  '項目照片': ('Word photos', 'Photos du mot'),
  'e.g. 陽台': ('e.g. balcony (in Chinese)', 'Ex. : balcon (en chinois)'),
  '答對了': ('Correct', 'Bonne réponse'),
  '答錯了': ('Incorrect', 'Mauvaise réponse'),
  '查看完整單字': ('View full word details', 'Voir tous les détails'),
  '正在連接詞庫…': ('Connecting to dictionary…', 'Connexion au dictionnaire…'),
  '已連接詞庫 · 每 30 秒自動更新': (
    'Dictionary connected · updates every 30 seconds',
    'Dictionnaire connecté · actualisation toutes les 30 secondes'
  ),
  '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試': (
    'Offline · using saved dictionary; retrying later',
    'Hors ligne · dictionnaire enregistré utilisé ; nouvel essai plus tard'
  ),
  '字母 A–Z': ('Alphabetical A–Z', 'Ordre alphabétique A–Z'),
  '最近更新': ('Recently updated', 'Mise à jour récente'),
  '下次出現': ('Next review', 'Prochaine révision'),
  '新單字': ('New word', 'Nouveau mot'),
  '複習中': ('Reviewing', 'En révision'),
  '穩定': ('Stable', 'Stable'),
  '未建卡': ('No card', 'Sans carte'),
  '缺音標': ('Missing pronunciation', 'Prononciation manquante'),
  '缺例句': ('Missing examples', 'Exemples manquants'),
  '缺例句翻譯': (
    'Missing example translations',
    'Traductions d’exemples manquantes'
  ),
  '缺相關詞彙': ('Missing related words', 'Mots associés manquants'),
  '資料取得失敗': ('Data unavailable', 'Données indisponibles'),
  '名詞': ('Noun', 'Nom'),
  '動詞': ('Verb', 'Verbe'),
  '形容詞': ('Adjective', 'Adjectif'),
  '副詞': ('Adverb', 'Adverbe'),
  '代名詞': ('Pronoun', 'Pronom'),
  '介系詞': ('Preposition', 'Préposition'),
  '連接詞': ('Conjunction', 'Conjonction'),
  '感嘆詞': ('Interjection', 'Interjection'),
  '限定詞': ('Determiner', 'Déterminant'),
  '數詞': ('Numeral', 'Numéral'),
  '片語': ('Phrase', 'Expression'),
  '專有名詞': ('Proper noun', 'Nom propre'),
  '其他詞性': ('Other', 'Autre'),
  '入門（A1）': ('Beginner (A1)', 'Débutant (A1)'),
  '基礎（A2）': ('Elementary (A2)', 'Élémentaire (A2)'),
  '中階（B1）': ('Intermediate (B1)', 'Intermédiaire (B1)'),
  '中高階（B2）': ('Upper intermediate (B2)', 'Intermédiaire avancé (B2)'),
  '進階（C1）': ('Advanced (C1)', 'Avancé (C1)'),
  '精通（C2）': ('Proficient (C2)', 'Maîtrise (C2)'),
  '歡迎使用拍照學單字': (
    'Welcome to photo vocabulary',
    'Bienvenue dans l’apprentissage par photos'
  ),
  '用喜歡的照片學單字。先選想學的語言和你的母語。': (
    'Learn with your favourite photos. Choose your learning and native languages.',
    'Apprenez avec vos photos préférées. Choisissez la langue étudiée et votre langue maternelle.'
  ),
  '我想學': ('I want to learn', 'Je veux apprendre'),
  '我的母語（翻譯與提示會用這個語言）': (
    'My native language (for translations and hints)',
    'Ma langue maternelle (traductions et indices)'
  ),
  '第一階段尚未提供詞庫': (
    'Dictionary not yet available',
    'Dictionnaire pas encore disponible'
  ),
  '第一階段尚未提供翻譯資料': (
    'Translations not yet available',
    'Traductions pas encore disponibles'
  ),
  '下一步': ('Next', 'Suivant'),
  '上一步': ('Previous', 'Précédent'),
  '你對英文熟悉嗎？': (
    'How well do you know English?',
    'Quel est votre niveau d’anglais ?'
  ),
  '你對法文熟悉嗎？': (
    'How well do you know French?',
    'Quel est votre niveau de français ?'
  ),
  '用來決定一開始建議的單字難度，之後會依你的使用情況慢慢調整。': (
    'This sets your starting difficulty, which gradually adapts to your activity.',
    'Cela définit votre difficulté initiale, qui s’adapte progressivement à votre activité.'
  ),
  '從未接觸': ('New to the language', 'Je découvre la langue'),
  '幾乎沒學過': ('Little or no experience', 'Peu ou pas d’expérience'),
  '會基礎單字': ('Know basic words', 'Je connais les bases'),
  '認得日常生活的簡單單字': (
    'Recognise simple everyday words',
    'Je reconnais les mots simples du quotidien'
  ),
  '已學一段時間': ('Some experience', 'J’ai déjà étudié la langue'),
  '能讀懂簡單的文章': ('Can read simple texts', 'Je comprends les textes simples'),
  '熟練': ('Confident', 'À l’aise'),
  '大部分內容都看得懂': (
    'Understand most content',
    'Je comprends la plupart des contenus'
  ),
  '從基礎開始': ('Start with the basics', 'Commencer par les bases'),
  '開始使用': ('Get started', 'Commencer'),
  '想測看看？試試單字程度（可略過）': (
    'Try a vocabulary check (optional)',
    'Tester mon vocabulaire (facultatif)'
  ),
  '試試你認得哪些單字': (
    'Which words do you recognise?',
    'Quels mots reconnaissez-vous ?'
  ),
  '一次只看 3 個字。認得就點一下，不認得也沒關係。': (
    'Three words at a time. Tap the ones you know; it’s fine if you don’t.',
    'Trois mots à la fois. Touchez ceux que vous connaissez ; sinon, aucun souci.'
  ),
  '繼續': ('Continue', 'Continuer'),
  '都不認識，從基礎開始': ('Start with the basics', 'Commencer par les bases'),
  '先到這裡，開始學習': (
    'Finish check and start learning',
    'Terminer le test et commencer'
  ),
  '你改過的欄位之後不會被自動更新覆蓋。': (
    'Your edits will not be overwritten by automatic updates.',
    'Vos modifications seront conservées lors des mises à jour automatiques.'
  ),
  '拍照': ('Camera', 'Photo'),
  '相片冊': ('Albums', 'Albums'),
  '複習': ('Review', 'Révision'),
  '單字本': ('Words', 'Mots'),
  '設定': ('Settings', 'Réglages'),
  '隱私': ('Privacy', 'Confidentialité'),
  '分享使用統計': ('Share usage statistics', 'Partager les statistiques d’usage'),
  '只送匿名的操作紀錄，用來改善 App；關閉不影響任何功能。': (
    'Only anonymous activity is sent, to improve the app. Turning it off changes nothing.',
    'Seules des activités anonymes sont envoyées, pour améliorer l’app. Désactiver ne change rien.'
  ),
  '查看隱私權政策': ('View privacy policy', 'Voir la politique de confidentialité'),
  '隱私權政策': ('Privacy policy', 'Politique de confidentialité'),
  '本政策說明「拍照學單字」如何處理資料。分享使用統計預設是關閉的。': (
    'This policy explains how 拍照學單字 handles data. Sharing usage statistics is off by default.',
    'Cette politique explique comment 拍照學單字 traite les données. Le partage des statistiques est désactivé par défaut.'
  ),
  '使用統計': ('Usage statistics', 'Statistiques d’usage'),
  '打開「分享使用統計」之後，操作紀錄會送到 PostHog（主機 us.i.posthog.com）。送出的只有：這次安裝產生的隨機代號、開啟 App、所在分頁、學習語言、母語、程度與程度來源、有沒有加入照片或單字（不含照片和單字本身）、複習開始與結束，以及單次作答的評分、題型、對錯、提示次數、作答時間與下次間隔天數。不送姓名、帳號、電子郵件或廣告識別碼。隨時可以在設定裡關掉；還沒送出的紀錄會一併捨棄。':
      (
    'After you turn on Share usage statistics, activity is sent to PostHog (host us.i.posthog.com). We send only: a random id created for this install, app opens, the current tab, learning language, native language, level and how the level was chosen, whether a photo or word was added (not the photo or the word), review start and finish, and for each answer the rating, exercise type, right or wrong, hint count, time spent and the next interval in days. We do not send your name, account, email or advertising id. You can turn this off in Settings at any time; events not yet sent are discarded.',
    'Après avoir activé le partage, l’activité est envoyée à PostHog (hôte us.i.posthog.com). Nous envoyons seulement : un identifiant aléatoire créé pour cette installation, les ouvertures, l’onglet affiché, la langue étudiée, la langue maternelle, le niveau et son origine, l’ajout d’une photo ou d’un mot (sans la photo ni le mot), le début et la fin d’une révision, et pour chaque réponse la note, le type d’exercice, juste ou faux, le nombre d’indices, le temps et le prochain intervalle en jours. Pas de nom, de compte, d’e-mail ni d’identifiant publicitaire. Vous pouvez désactiver cela dans Réglages ; ce qui n’est pas encore envoyé est effacé.'
  ),
  '照片與辨識': ('Photos and recognition', 'Photos et reconnaissance'),
  '照片和字卡保存在這台裝置。使用辨識時，照片會傳到你設定的辨識伺服器，只在記憶體裡即時辨識，不會存成照片檔。伺服器可能留下辨識結果的文字快取（單字與分數，不含照片），以免同一張照片重複運算。照片不會送到分析服務。':
      (
    'Photos and cards stay on this device. When you use recognition, the photo is sent to the recognition server you configured, processed in memory at that moment, and not saved as a photo file. The server may keep a text cache of the result (words and scores, not the photo) so the same photo is not processed twice. Photos are not sent to the analytics service.',
    'Les photos et les cartes restent sur cet appareil. Pour la reconnaissance, la photo est envoyée au serveur que vous avez indiqué, traitée en mémoire sur le moment, et n’est pas enregistrée comme fichier photo. Le serveur peut garder un cache texte du résultat (mots et scores, pas la photo) pour ne pas retraiter la même photo. Les photos ne vont pas au service d’analyse.'
  ),
  '不做跨 App 追蹤': ('No cross-app tracking', 'Pas de suivi entre applications'),
  '本 App 只做自己的使用統計，不把資料拿去跟其他 App 或網站比對，也不使用廣告識別碼，所以不會跳出「允許追蹤」的詢問。': (
    'This app only measures its own use. It does not combine that data with other companies’ apps or websites, and it does not use an advertising id, so it does not ask for permission to track.',
    'Cette app ne mesure que son propre usage. Elle ne recoupe pas ces données avec les apps ou sites d’autres sociétés, et n’utilise pas d’identifiant publicitaire, donc elle ne demande pas l’autorisation de suivi.'
  ),
  '政策網頁': ('Policy page', 'Page de la politique'),
  '政策網頁還沒有公開網址。這份說明就是目前的隱私權政策；公開後，App Store 會連到同一個內容。': (
    'The policy page does not have a public address yet. This screen is the privacy policy for now; once it is published, the App Store will link to the same text.',
    'La page n’a pas encore d’adresse publique. Cet écran est la politique pour l’instant ; une fois publiée, l’App Store pointera vers le même texte.'
  ),
  '返回': ('Back', 'Retour'),
  '分享': ('Share', 'Partager'),
  '關閉': ('Close', 'Fermer'),
  '取消': ('Cancel', 'Annuler'),
  '儲存': ('Save', 'Enregistrer'),
  '完成': ('Done', 'Terminé'),
  '好': ('OK', 'OK'),
  '新增': ('Add', 'Ajouter'),
  '復原': ('Restore', 'Rétablir'),
  '重試': ('Retry', 'Réessayer'),
  '全部': ('All', 'Tout'),
  '收合': ('Collapse', 'Réduire'),
  '收合項目': ('Collapse items', 'Réduire la liste'),
  '顯示全部': ('Show all', 'Tout afficher'),
  '語言': ('Languages', 'Langues'),
  '學習語言': ('Learning language', 'Langue étudiée'),
  '母語': ('Native language', 'Langue maternelle'),
  '更多學習語言即將推出': (
    'More learning languages coming soon',
    'Davantage de langues bientôt disponibles'
  ),
  '學習語言和母語不能相同': (
    'Choose different learning and native languages',
    'Choisissez deux langues différentes'
  ),
  '每個學習語言有自己的相片冊、單字、卡片與程度。': (
    'Each learning language has its own albums, words, cards and level.',
    'Chaque langue étudiée a ses albums, mots, cartes et niveau.'
  ),
  '介面語言跟著母語切換。': (
    'The interface language follows your native language.',
    'La langue de l’interface suit votre langue maternelle.'
  ),
  '英文（English）': ('English', 'Anglais (English)'),
  '法文（Français）': ('French (Français)', 'Français'),
  '繁體中文': ('Traditional Chinese', 'Chinois traditionnel'),
  '發音腔調': ('Pronunciation accent', 'Accent'),
  '卡片樣式': ('Card style', 'Style des cartes'),
  '經典': ('Classic', 'Classique'),
  '簡潔留白': ('Clean', 'Épuré'),
  '圖片沉浸': ('Photo-first', 'Immersif'),
  '活潑遊戲': ('Playful', 'Ludique'),
  '只改變複習卡片的外觀，內容和複習方式不變。': (
    'Changes only how review cards look; their content and reviews stay the same.',
    'Change seulement l’apparence des cartes ; contenu et révisions restent identiques.'
  ),
  '英式（en-GB）': ('British (en-GB)', 'Britannique (en-GB)'),
  '美式（en-US）': ('American (en-US)', 'Américain (en-US)'),
  '點一下試聽「water」；單字頁、單字本和複習卡都用這個腔調。': (
    'Tap to hear “water”; word pages, the Words tab and review cards use this accent.',
    'Touchez pour entendre « water » ; fiches de mots, onglet Mots et cartes utilisent cet accent.'
  ),
  '複習卡翻到背面時英式、美式各唸一次。沒有這個腔調錄音的字，播現有的錄音。': (
    'The back of a review card plays British, then American. Words with no recording in this accent play the one they have.',
    'Le verso d’une carte joue l’accent britannique puis américain. Un mot sans enregistrement dans cet accent joue celui qu’il a.'
  ),
  '單字難度': ('Word difficulty', 'Difficulté des mots'),
  '快速詞彙檢查': ('Quick vocabulary check', 'Test rapide de vocabulaire'),
  '依你的使用情況調整': ('Adjusted from your activity', 'Ajusté selon votre activité'),
  '你設定的': ('Set by you', 'Défini par vous'),
  '自評': ('Self-assessment', 'Autoévaluation'),
  'App 自動調整': ('Auto-adjusted by the app', 'Ajusté par l’app'),
  '新照片的單字以下面選的程度為主，App 會依你的複習慢慢調整。': (
    'New photos pick words around the level chosen below; the app adjusts it as you review.',
    'Les nouvelles photos utilisent le niveau choisi ci-dessous ; l’app l’ajuste au fil de vos révisions.'
  ),
  '新照片的單字以這個程度為主，App 會依你的複習慢慢調整。': (
    'New photos pick words around this level; the app adjusts it as you review.',
    'Les nouvelles photos utilisent ce niveau ; l’app l’ajuste au fil de vos révisions.'
  ),
  '累積至少 20 次使用紀錄後，程度會依你的評分、左滑與轉盤自動調整，一次最多一級。照片詳情的難度轉盤只影響那一張照片。': (
    'After at least 20 interactions, your ratings, swipes and difficulty dial adjust the level, one step at a time. The dial in photo details affects only that photo.',
    'Après au moins 20 interactions, vos notes, balayages et le cadran ajustent le niveau, un palier à la fois. Le cadran des détails ne concerne que cette photo.'
  ),
  '網頁版會自動連接這台電腦的照片辨識服務，不用填網址或金鑰。只有使用其他服務時才需要修改。連不上時照片會先排隊，恢復連線後自動處理。': (
    'The web app connects to this computer’s recognition service automatically. Only change these settings for another service. Photos wait offline and resume when connected.',
    'L’application web se connecte automatiquement au service de cet ordinateur. Modifiez ces réglages pour un autre service. Les photos attendent hors ligne puis reprennent à la connexion.'
  ),
  '留空時用手機本機辨識照片；填入服務網址與金鑰則改用該服務。連不上時照片會先排隊，恢復連線後自動處理。': (
    'Leave empty to recognise photos on the phone; enter a service address and key to use that service instead. Photos wait offline and resume when connected.',
    'Laissez vide pour reconnaître les photos sur le téléphone ; saisissez l’adresse et la clé d’un service pour l’utiliser. Les photos attendent hors ligne puis reprennent à la connexion.'
  ),
  '服務網址': ('Service URL', 'URL du service'),
  '連線金鑰（API Key）': ('API key', 'Clé API'),
  '請先填寫服務網址': (
    'Enter the service URL first',
    'Saisissez d’abord l’URL du service'
  ),
  '測試中…': ('Testing…', 'Test en cours…'),
  '測試連線': ('Test connection', 'Tester la connexion'),
  '✕ 服務有回應，但 AI 模型沒有啟動': (
    '✕ Service responded, but the AI model is not running',
    '✕ Le service répond, mais le modèle IA est arrêté'
  ),
  '✕ 服務正常，但 API Key 不正確': (
    '✕ Service is online, but the API key is incorrect',
    '✕ Le service fonctionne, mais la clé API est incorrecte'
  ),
  '進階設定': ('Advanced settings', 'Réglages avancés'),
  '照片辨識連線': (
    'Photo recognition connection',
    'Connexion à la reconnaissance photo'
  ),
  '照片辨識暫時連不上：新照片會先排隊，連上後自動辨識，不用處理': (
    'Photo recognition is offline for now: new photos wait in line and are recognised once it reconnects. Nothing to do.',
    'Reconnaissance photo hors ligne pour l’instant : les nouvelles photos attendent et seront reconnues à la reconnexion. Rien à faire.'
  ),
  '照片辨識設定有誤，新照片無法辨識，點開修正': (
    'Photo recognition settings are wrong, so new photos can’t be recognised. Open to fix.',
    'Les réglages de reconnaissance photo sont incorrects : les nouvelles photos ne peuvent pas être reconnues. Ouvrir pour corriger.'
  ),
  '複習安排': ('Review schedule', 'Calendrier de révision'),
  '越高，單字越常出現。預設 90%。': (
    'Higher values mean more frequent reviews. Default: 90%.',
    'Une valeur élevée augmente la fréquence des révisions. Par défaut : 90 %.'
  ),
  '卡片背面順序': ('Card back order', 'Ordre du verso des cartes'),
  '詞庫連線': ('Dictionary connection', 'Connexion au dictionnaire'),
  '資料': ('Data', 'Données'),
  '字卡和複習紀錄保存在此瀏覽器。': (
    'Cards and review history are saved in this browser.',
    'Les cartes et l’historique sont enregistrés dans ce navigateur.'
  ),
  '字卡和複習紀錄保存在此裝置。': (
    'Cards and review history are saved on this device.',
    'Les cartes et l’historique sont enregistrés sur cet appareil.'
  ),
  '資料庫': ('Database', 'Base de données'),
  '我的單字本': ('My words', 'Mes mots'),
  '我的相片冊': ('My albums', 'Mes albums'),
  '資料庫單字本': ('Database words', 'Mots du dictionnaire'),
  '資料庫相片冊': ('Database photos', 'Photos du dictionnaire'),
  '正在取得資料庫內容': ('Loading database content', 'Chargement du dictionnaire'),
  '重新連線': ('Reconnect', 'Reconnecter'),
  '搜尋{L}或{N}': ('Search {L} or {N}', 'Rechercher en {L} ou en {N}'),
  '搜尋圖片上的{L}或{N}標籤': (
    'Search photo labels in {L} or {N}',
    'Rechercher les étiquettes en {L} ou en {N}'
  ),
  '搜尋照片': ('Search photos', 'Rechercher des photos'),
  '新增單字': ('Add word', 'Ajouter un mot'),
  '新增單字標籤': ('Add word label', 'Ajouter une étiquette'),
  '開始複習': ('Start review', 'Commencer la révision'),
  '還在學': ('Learning', 'En cours'),
  '學習中': ('Learning', 'En cours'),
  '已學會': ('Learned', 'Acquis'),
  '學習狀態': ('Learning status', 'État d’apprentissage'),
  '全部狀態': ('All statuses', 'Tous les états'),
  '全部詞性': ('All parts of speech', 'Toutes les catégories'),
  '全部等級': ('All levels', 'Tous les niveaux'),
  '等級篩選': ('Filter by level', 'Filtrer par niveau'),
  '缺漏欄位': ('Missing fields', 'Champs manquants'),
  '不限': ('Any', 'Tous'),
  '進階篩選與排序': ('Filters and sorting', 'Filtres et tri'),
  '沒有符合條件的單字': ('No matching words', 'Aucun mot correspondant'),
  '沒有符合的單字': ('No matching words', 'Aucun mot correspondant'),
  '沒有符合的圖片': ('No matching photos', 'Aucune photo correspondante'),
  '請嘗試調整搜尋關鍵字或進階篩選條件': (
    'Try changing your search or filters',
    'Modifiez la recherche ou les filtres'
  ),
  '單字詳情': ('Word details', 'Détails du mot'),
  '{N}意思尚未補齊': ('{N} meaning pending', 'Sens en {N} en attente'),
  '{N}意思待補齊': ('{N} meaning pending', 'Sens en {N} en attente'),
  '{N}意思尚未補齊，連線後會自動更新。': (
    '{N} meaning pending; it will update when connected.',
    'Le sens en {N} sera ajouté à la connexion.'
  ),
  '部分內容待補齊': ('Some content is pending', 'Contenu partiellement en attente'),
  '部分內容尚未補齊，詞庫更新後會自動補上。': (
    'Some content is pending and will appear after a dictionary update.',
    'Le contenu manquant apparaîtra après la mise à jour du dictionnaire.'
  ),
  '資料取得失敗，稍後自動重試': (
    'Could not load data; retrying later',
    'Chargement impossible ; nouvel essai plus tard'
  ),
  '加入我的單字本與複習': (
    'Add to my words and review',
    'Ajouter à mes mots et aux révisions'
  ),
  '加入單字本（{N}補齊後排進複習）': (
    'Add to my words (review starts when the {N} meaning is ready)',
    'Ajouter à mes mots (révision quand le sens en {N} sera disponible)'
  ),
  '已在我的單字本 ✓': ('Already in my words ✓', 'Déjà dans mes mots ✓'),
  '這個字還在補齊資料': (
    'This word’s details are still being filled in',
    'Les informations de ce mot sont en cours d’ajout'
  ),
  '已加入我的單字本與複習': (
    'Added to my words and review',
    'Ajouté à mes mots et aux révisions'
  ),
  '已加入我的單字本；{N}意思補齊後會自動排進複習': (
    'Added to my words; review starts when the {N} meaning is ready',
    'Ajouté à mes mots ; la révision commencera lorsque le sens en {N} sera disponible'
  ),
  '這個單字已在我的單字本': (
    'This word is already in my words',
    'Ce mot est déjà dans mes mots'
  ),
  '這個單字已從資料庫移除': (
    'This word was removed from the database',
    'Ce mot a été retiré du dictionnaire'
  ),
  '資料庫尚未加入這個單字的圖片': (
    'No database photo for this word yet',
    'Aucune photo pour ce mot dans le dictionnaire'
  ),
  '管理這個單字': ('Manage this word', 'Gérer ce mot'),
  '可查看意思、修改名稱或標為已學會。': (
    'View the meaning, edit the name or mark as learned.',
    'Consultez le sens, modifiez le nom ou marquez le mot comme acquis.'
  ),
  '標為已學會': ('Mark as learned', 'Marquer comme acquis'),
  '我已經會了（移到已學會）': (
    'I know this (mark as learned)',
    'Je connais ce mot (marquer comme acquis)'
  ),
  '復原學習': ('Resume learning', 'Reprendre l’apprentissage'),
  '已從「已學會」放回複習': ('Returned to review', 'Remis en révision'),
  '播放發音': ('Play pronunciation', 'Écouter la prononciation'),
  '聽發音': ('Listen', 'Écouter'),
  '查看更多例句': ('More examples', 'Plus d’exemples'),
  '更多單字資訊': ('More word information', 'Plus d’informations'),
  '更多意思': ('More meanings', 'Autres sens'),
  '實用例句': ('Useful examples', 'Exemples utiles'),
  '例句與翻譯': ('Examples and translations', 'Exemples et traductions'),
  '例句：AI 產生': ('Examples: AI-generated', 'Exemples générés par IA'),
  '  AI 翻譯': ('  AI translation', '  Traduction IA'),
  '中文': ('Chinese', 'Chinois'),
  '英文': ('English', 'Anglais'),
  '{L}單字': ('{L} word', 'Mot en {L}'),
  '照片裡的{L}單字：': ('{L} words in this photo: ', 'Mots en {L} de cette photo : '),
  '詞庫尚未提供{N}意思': (
    'The dictionary has no {N} meaning yet',
    'Le dictionnaire n’a pas encore le sens en {N}'
  ),
  '{N}意思': ('{N} meaning', 'Sens en {N}'),
  '{N}釋義': ('{N} definition', 'Définition en {N}'),
  '釋義': ('Definition', 'Définition'),
  '逐義釋義': ('Definitions by sense', 'Définitions par sens'),
  '各詞性釋義': ('Definitions by part of speech', 'Définitions par catégorie'),
  '詞性與意思': ('Parts of speech and meanings', 'Catégories et sens'),
  '詞性': ('Part of speech', 'Catégorie grammaticale'),
  '例句': ('Examples', 'Exemples'),
  '近義詞': ('Synonyms', 'Synonymes'),
  '反義詞': ('Antonyms', 'Antonymes'),
  '同音詞': ('Homophones', 'Homophones'),
  '近音詞': ('Similar-sounding words', 'Mots de sonorité proche'),
  '拼寫相似詞': ('Similar spellings', 'Orthographes proches'),
  '衍生詞': ('Derived words', 'Mots dérivés'),
  '相關詞': ('Related words', 'Mots associés'),
  '詞形變化': ('Inflections', 'Flexions'),
  '詞形與衍生': ('Forms and derivatives', 'Formes et dérivés'),
  '詞源': ('Etymology', 'Étymologie'),
  '構詞': ('Word formation', 'Formation du mot'),
  '資料來源': ('Sources', 'Sources'),
  '意思相近的單字': ('Similar meanings', 'Sens proches'),
  '意思相反的單字': ('Opposite meanings', 'Sens opposés'),
  '中性／通用': ('Neutral / general', 'Neutre / courant'),
  '口語': ('Informal', 'Familier'),
  '書面語': ('Formal', 'Soutenu'),
  '俚語': ('Slang', 'Argot'),
  '未分級': ('Unrated', 'Sans niveau'),
  '未收錄': ('Not listed', 'Non répertorié'),
  '有你修改過的欄位': ('Contains your edits', 'Contient vos modifications'),
  '刪除此卡片': ('Remove this card', 'Retirer cette carte'),
  '想複習哪一本？': ('Which one to review?', 'Quel paquet réviser ?'),
  // 問題回報 #534 (M214).
  '這次忘記的字': ('Forgotten this time', 'Oubliés cette fois'),
  '今天的份量已完成。想多練習可以繼續，想休息時按左上角結束。': (
    'Today’s share is done. Keep practising if you like; tap the top-left button to stop.',
    'La part du jour est faite. Continuez si vous voulez ; touchez en haut à gauche pour arrêter.'
  ),
  '點一格就開始；做完還可以繼續練習，想休息時按左上角結束。': (
    'Tap a tile to start. Keep practising after you finish, or stop with the top-left button.',
    'Touchez une tuile pour commencer. Continuez après la séance, ou arrêtez avec le bouton en haut à gauche.'
  ),
  '綜合': ('All together', 'Tout'),
  '今天新加的單字': ('Added today', 'Ajoutés aujourd’hui'),
  '弱項單字': ('Weak words', 'Mots faibles'),
  '上次複習': ('Last reviewed', 'Dernière révision'),
  '今天沒有到期': ('Nothing due today', 'Rien à réviser aujourd’hui'),
  '＋ 下載相片冊': ('+ Download albums', '+ Télécharger des albums'),
  '還沒有相片：去拍照，或下載別人的相片冊': (
    'No photos yet: take some, or download someone else’s album',
    'Pas encore de photos : prenez-en, ou téléchargez un album'
  ),
  '想複習的時候就開始吧': ('Ready when you are', 'Révisez à votre rythme'),
  '先想答案，再翻面；隨時可以結束。': (
    'Think of the answer, then flip. Stop whenever you like.',
    'Cherchez la réponse, puis retournez la carte. Arrêtez quand vous voulez.'
  ),
  '等待詞庫補齊': ('Waiting for dictionary content', 'En attente du dictionnaire'),
  '現在沒有需要複習的卡片': (
    'No cards to review right now',
    'Aucune carte à réviser pour le moment'
  ),
  '單字的{N}意思補齊後，會自動加入複習。': (
    'Words enter review automatically when their {N} meanings are ready.',
    'Les mots seront ajoutés aux révisions lorsque leur sens en {N} sera disponible.'
  ),
  '在照片詳情挑幾個單字，或下載卡片集，就會變成卡片。': (
    'Choose words from a photo or download a deck to create cards.',
    'Choisissez des mots sur une photo ou téléchargez un paquet pour créer des cartes.'
  ),
  '還沒有單字': ('No words yet', 'Pas encore de mots'),
  '去拍照，或到卡片集下載卡片集，單字就會出現在這裡': (
    'Take a photo or download a deck and your words will show up here',
    'Prenez une photo ou téléchargez un paquet : vos mots apparaîtront ici'
  ),
  '重新命名相簿': ('Rename album', "Renommer l'album"),
  '還沒有相片：去拍照，或到卡片集下載圖片集': (
    'No photos yet: take one, or download a picture deck',
    "Pas encore de photos : prenez-en une ou téléchargez un jeu d'images"
  ),
  '圖片集': ('Picture decks', "Jeux d'images"),
  '單字集': ('Word deck', 'Jeu de mots'),
  '張': ('photos', 'photos'),
  '字': ('words', 'mots'),
  'English Card 編輯部': (
    'English Card Editors',
    'Équipe éditoriale English Card'
  ),
  '去拍照選單字': (
    'Take a photo to find words',
    'Photographier pour trouver des mots'
  ),
  '查看相片冊': ('View albums', 'Voir les albums'),
  '今天先到這裡': ('That’s all for now', 'C’est tout pour le moment'),
  '這次的練習先到這裡。\n想複習時，再回來就好。': (
    'That’s all for this session.\nCome back whenever you want to review.',
    'Cette séance est terminée.\nRevenez quand vous souhaitez réviser.'
  ),
  '顯示答案': ('Show answer', 'Afficher la réponse'),
  '空白鍵': ('Space', 'Espace'),
  '送出答案': ('Submit answer', 'Valider la réponse'),
  '輸入缺少的單字': ('Enter the missing word', 'Saisissez le mot manquant'),
  '需要提示': ('Need a hint', 'Besoin d’un indice'),
  '提示已顯示': ('Hint shown', 'Indice affiché'),
  '顯示字首提示': ('Show first-letter hint', 'Afficher la première lettre'),
  '字首提示': ('First-letter hint', 'Première lettre'),
  '母語提示': ('Native-language hint', 'Indice en langue maternelle'),
  '母語說明＋照片': ('Native meaning + photo', 'Sens + photo'),
  '先在心裡想出這個字，再按「顯示答案」。': (
    'Recall the word, then select “Show answer”.',
    'Retrouvez le mot, puis sélectionnez « Afficher la réponse ».'
  ),
  '這一組不相符，再試一次。': (
    'These do not match. Try again.',
    'Ces éléments ne correspondent pas. Réessayez.'
  ),
  '句子填空': ('Fill in the blank', 'Phrase à compléter'),
  '相似詞配對': ('Match related words', 'Associer les mots'),
  '看圖選單字': (
    'Choose the word for the photo',
    'Choisir le mot correspondant à la photo'
  ),
  '稍後再出現': ('Appears again later', 'Réapparaît plus tard'),
  '拍照學單字': ('Learn words with photos', 'Apprendre avec des photos'),
  '拍照或選一張照片，找出生活中的{L}單字': (
    'Take or choose a photo to find {L} words around you',
    'Prenez ou choisissez une photo pour trouver les mots {L} autour de vous'
  ),
  '先選一張照片開始學習': (
    'Choose a photo to start learning',
    'Choisissez une photo pour commencer'
  ),
  '從相簿選擇': ('Choose from gallery', 'Choisir dans la galerie'),
  '最近照片': ('Recent photos', 'Photos récentes'),
  '最近的照片': ('Recent photos', 'Photos récentes'),
  '查看最近照片的單字': (
    'View words in recent photos',
    'Voir les mots des photos récentes'
  ),
  '查看這張照片的單字': ('View words in this photo', 'Voir les mots de cette photo'),
  '最近一張照片的單字': ('Words in your last photo', 'Mots de votre dernière photo'),
  '開啟最近的照片': ('Open recent photo', 'Ouvrir la photo récente'),
  '正在讀取最近照片…': ('Loading recent photos…', 'Chargement des photos récentes…'),
  '還沒有照片，先拍一張吧！': (
    'No photos yet. Take your first one!',
    'Aucune photo. Prenez la première !'
  ),
  '相機未啟用': ('Camera is off', 'Appareil photo désactivé'),
  '正在開啟相機…': ('Opening camera…', 'Ouverture de l’appareil photo…'),
  '目前無法使用相機': ('Camera is unavailable', 'Appareil photo indisponible'),
  '相機權限未開啟': (
    'Camera permission is off',
    'Autorisation de l’appareil photo désactivée'
  ),
  '開啟權限說明': ('How to enable permission', 'Comment activer l’autorisation'),
  '請到手機「設定」→ 找到本 App → 開啟「相機」權限，再回來按「重試相機」。': (
    'Open Settings, find this app, turn on Camera access, then come back and tap “Retry camera”.',
    'Ouvrez Réglages, trouvez cette app, activez l’accès à l’appareil photo, puis revenez et touchez « Réessayer l’appareil photo ».'
  ),
  '找不到相機': ('No camera found', 'Aucun appareil photo trouvé'),
  '重試相機': ('Retry camera', 'Réessayer l’appareil photo'),
  '這台裝置不支援閃光燈': (
    'Flash is not supported on this device',
    'Cet appareil ne dispose pas de flash'
  ),
  '開啟閃光燈': ('Turn flash on', 'Activer le flash'),
  '關閉閃光燈': ('Turn flash off', 'Désactiver le flash'),
  'AI 辨識就緒': ('AI recognition ready', 'Reconnaissance IA prête'),
  'AI 離線 · 照片會先排隊': (
    'AI offline · photos will wait',
    'IA hors ligne · photos en attente'
  ),
  '照片辨識尚未連線': (
    'Photo recognition is offline',
    'Reconnaissance des photos hors ligne'
  ),
  '只找照片裡的{L}字・物品辨識未連線': (
    'Printed {L} text only · object recognition off',
    'Texte {L} imprimé seulement · objets non reconnus'
  ),
  '設定辨識': ('Set up recognition', 'Configurer la reconnaissance'),
  '照片詳情': ('Photo details', 'Détails de la photo'),
  '照片名稱': ('Photo name', 'Nom de la photo'),
  '照片情境': ('Photo context', 'Contexte de la photo'),
  '選擇照片': ('Choose photos', 'Choisir des photos'),
  '選擇新照片': ('Choose new photo', 'Choisir une nouvelle photo'),
  '已選照片與範例': (
    'Selected photos and examples',
    'Photos sélectionnées et exemples'
  ),
  '範例照片': ('Example photos', 'Photos d’exemple'),
  '不要這張': ('Discard this photo', 'Ne pas garder cette photo'),
  '照片未儲存': ('Photo not saved', 'Photo non enregistrée'),
  '存到相片冊': ('Save to album', 'Enregistrer dans un album'),
  '這張照片已經加入過': ('This photo is already added', 'Cette photo est déjà ajoutée'),
  '仍要再加入': ('Add anyway', 'Ajouter quand même'),
  '打開原本的照片': ('Open the existing photo', 'Ouvrir la photo existante'),
  '辛苦了。每張卡下次出現的時間已經排好，\n想複習時，再回來就好。': (
    'Nice work. Each card\'s next time is scheduled;\ncome back whenever you like.',
    'Bravo. La prochaine fois de chaque carte est planifiée ;\nrevenez quand vous voulez.'
  ),
  '相片冊名稱': ('Album name', 'Nom de l’album'),
  '＋ 新相片冊': ('＋ New album', '＋ Nouvel album'),
  '這個分類還沒有相片冊': (
    'No albums in this category yet',
    'Aucun album dans cette catégorie'
  ),
  '圖片暫時無法載入': ('Photo could not load', 'Impossible de charger la photo'),
  '圖片暫時無法載入，稍後再試': (
    'Photo could not load. Try again later.',
    'Impossible de charger la photo. Réessayez plus tard.'
  ),
  '正在載入圖片…': ('Loading photo…', 'Chargement de la photo…'),
  '重試圖片': ('Retry photo', 'Recharger la photo'),
  '拖曳到圖片': ('Drag onto photo', 'Glisser sur la photo'),
  '修改標籤': ('Edit label', 'Modifier l’étiquette'),
  '查看單字': ('View word', 'Voir le mot'),
  '程度': ('Level', 'Niveau'),
  '簡單一點': ('Easier', 'Plus facile'),
  '難一點': ('Harder', 'Plus difficile'),
  '多看動詞': ('More verbs', 'Plus de verbes'),
  '多看形容詞': ('More adjectives', 'Plus d’adjectifs'),
  '為什麼是這些字？': ('Why these words?', 'Pourquoi ces mots ?'),
  '取消鎖定': ('Unlock', 'Déverrouiller'),
  '鎖定（調整難度時保留）': (
    'Lock (keep when adjusting difficulty)',
    'Verrouiller (conserver lors du réglage)'
  ),
  '正在找照片裡的單字…': (
    'Finding words in the photo…',
    'Recherche de mots dans la photo…'
  ),
  '正在讀照片裡的文字…': (
    'Reading the text in the photo…',
    'Lecture du texte de la photo…'
  ),
  '處理中…': ('Processing…', 'Traitement…'),
  '補充候選詞…': ('Finding more candidates…', 'Recherche d’autres mots…'),
  '正在整理單字內容…': ('Preparing word content…', 'Préparation des mots…'),
  '單字待補齊': ('Word content pending', 'Contenu du mot en attente'),
  '可離開此頁，會繼續處理；請保持 App 開啟。': (
    'You can leave this page; keep the app open to continue processing.',
    'Vous pouvez quitter cette page ; gardez l’application ouverte pour poursuivre le traitement.'
  ),
  '等級（可不選）': ('Level (optional)', 'Niveau (facultatif)'),
  '請填寫{L}單字與{N}釋義': (
    'Enter a {L} word and {N} definition',
    'Saisissez un mot en {L} et sa définition en {N}'
  ),
  '音標、例句與翻譯會在背景自動補上。': (
    'Pronunciation, examples and translations are added in the background.',
    'La prononciation, les exemples et les traductions sont ajoutés en arrière-plan.'
  ),
  '位置不正確，詞籤已回到原位，請再試一次。': (
    'Invalid position. The label was restored; try again.',
    'Position incorrecte. L’étiquette a été rétablie ; réessayez.'
  ),
  '這張照片已從相片冊移除。\n手機相簿裡的原始照片不受影響。': (
    'This photo was removed from the album.\nThe original in your gallery is unchanged.',
    'Cette photo a été retirée de l’album.\nL’original dans votre galerie est conservé.'
  ),
  '學習洞察': ('Learning insights', 'Aperçu d’apprentissage'),
  '複習次數': ('Reviews', 'Révisions'),
  '關於': ('About', 'À propos'),
  '資料來源與授權': ('Data sources and licenses', 'Sources de données et licences'),
  '照片上的單字標示': ('Word labels on photos', 'Étiquettes de mots sur les photos'),
  '複習卡片背面的照片上，顯示這個單字的標籤。': (
    'On the back of review cards, show this word’s label on the photo.',
    'Au dos des cartes, affiche l’étiquette de ce mot sur la photo.'
  ),
  '複習幾次之後，這裡會顯示你的複習次數、程度變化和弱項單字。': (
    'After a few reviews, your review counts, level changes and weak words appear here.',
    'Après quelques révisions, vos révisions, changements de niveau et mots faibles apparaîtront ici.'
  ),
  '複習這些字': ('Review these words', 'Réviser ces mots'),
  'CEFR 等級變化': ('CEFR level changes', 'Changements de niveau CECR'),
  '蘋果': ('Apple', 'Pomme'),
  '同義詞': ('Synonyms', 'Synonymes'),
  '近音字': ('Homophones', 'Homophones'),
  '容易混淆的字': ('Easily confused words', 'Mots souvent confondus'),
  '構詞拆解': ('Word parts', 'Décomposition'),
  '字首': ('Prefix', 'Préfixe'),
  '字根': ('Root', 'Racine'),
  '字尾': ('Suffix', 'Suffixe'),
  '單字': ('Word', 'Mot'),
  '英式': ('British', 'Britannique'),
  '美式': ('American', 'Américain'),
  // 問題回報 #724: an accent with no recording is a synthesized voice.
  '合成': ('Synthetic', 'Synthèse'),
  '收起': ('Show less', 'Réduire'),
  '哪個單字最適合這張照片？': (
    'Which word fits this photo best?',
    'Quel mot correspond le mieux à cette photo ?'
  ),
  // 法語模擬 A1: the other review prompts were still in Chinese.
  '把單字拖到照片中的正確位置': (
    'Drag the word to the right place in the photo',
    'Fais glisser le mot au bon endroit sur la photo'
  ),
  '把三個意思和單字配對': (
    'Match the three meanings with their words',
    'Associe les trois sens à leurs mots'
  ),
  '等級為詞頻估算': (
    'Level is estimated from word frequency',
    'Niveau estimé d’après la fréquence'
  ),
  '整張圖': ('Whole picture', 'Image entière'),
  '等級為詞頻估算。': (
    'Level is estimated from word frequency.',
    'Niveau estimé d’après la fréquence.'
  ),
  '估': ('est.', 'est.'),
  '入門': ('Beginner', 'Débutant'),
  '基礎': ('Elementary', 'Élémentaire'),
  '中階': ('Intermediate', 'Intermédiaire'),
  '中高階': ('Upper intermediate', 'Intermédiaire supérieur'),
  '進階': ('Advanced', 'Avancé'),
  '精通': ('Proficient', 'Maîtrise'),
  '複數': ('plural', 'pluriel'),
  '過去式': ('past tense', 'passé'),
  '現在式': ('present tense', 'présent'),
  '過去分詞': ('past participle', 'participe passé'),
  '現在分詞': ('present participle', 'participe présent'),
  '第三人稱單數': ('third-person singular', '3e personne du singulier'),
  '比較級': ('comparative', 'comparatif'),
  '最高級': ('superlative', 'superlatif'),
  '變化形': ('inflected form', 'forme fléchie'),
  '陰性': ('feminine', 'féminin'),
  '陰性複數': ('feminine plural', 'féminin pluriel'),
  '陰陽性': ('gender', 'genre'),
  '陽性名詞': ('masculine noun', 'nom masculin'),
  '陰性名詞': ('feminine noun', 'nom féminin'),
  '陰陽同形名詞': ('masculine/feminine noun', 'nom masculin/féminin'),
  '只有複數': ('plural only', 'pluriel seulement'),
  '現在式 je': ('present je', 'présent je'),
  '現在式 tu': ('present tu', 'présent tu'),
  '現在式 il／elle': ('present il／elle', 'présent il／elle'),
  '現在式 nous': ('present nous', 'présent nous'),
  '現在式 vous': ('present vous', 'présent vous'),
  '現在式 ils／elles': ('present ils／elles', 'présent ils／elles'),
  '未完成過去式 je': ('imperfect je', 'imparfait je'),
  '簡單將來式 je': ('simple future je', 'futur simple je'),
  '複合時態助動詞': ('auxiliary (compound tenses)', 'auxiliaire (temps composés)'),
};

/// Language names for copy that names the language being learned (`{L}`) or
/// the meaning language, i.e. the learner's native one (`{N}`), each written
/// in the interface language (問題回報 #495: a French learner must not see
/// 「英文單字」 or 「find English words」).
const _languageNames = <String, Map<String, String>>{
  'en': {'zh-TW': '英文', 'en': 'English', 'fr': 'anglais'},
  'fr': {'zh-TW': '法文', 'en': 'French', 'fr': 'français'},
  'zh-TW': {'zh-TW': '中文', 'en': 'Chinese', 'fr': 'chinois'},
};

String translateUi(String source, String language, {String learning = 'en'}) {
  String fill(String text) => text
      .replaceAll('{L}', _languageNames[learning]?[language] ?? '')
      .replaceAll('{N}', _languageNames[language]?[language] ?? '');
  if (language != 'en' && language != 'fr') return fill(source);
  final entry = uiCatalog[source];
  if (entry != null) {
    return fill(language == 'fr' ? entry.$2 : entry.$1);
  }
  if (source.endsWith(' · 即將推出')) {
    final name = translateUi(source.replaceFirst(' · 即將推出', ''), language,
        learning: learning);
    return '$name · ${language == 'fr' ? 'Bientôt' : 'Coming soon'}';
  }
  for (final template in _templates) {
    final match = template.pattern.firstMatch(source);
    if (match == null) continue;
    final translation = language == 'fr' ? template.fr : template.en;
    return fill(translation.replaceAllMapped(
        RegExp(r'\{(\d+)\}'), (m) => match.group(int.parse(m[1]!) + 1)!));
  }
  return fill(_labelParts(source, language) ?? source);
}

/// 「un exemple（陽性名詞）」, 「動詞・名詞」: grammar labels joined by
/// （ ） ・ ； ： around untouched words. Only whole catalog entries are swapped.
String? _labelParts(String source, String language) {
  if (!RegExp(r'[一-鿿]').hasMatch(source)) return null;
  var changed = false;
  // ：joins a form's part of speech to its own meaning — dormant（現在分詞・
  // 形容詞：asleep） (卡 #516).
  // 「入門（A1） · 剛好」: the photo difficulty bar joins with a spaced ·.
  final out = source.splitMapJoin(RegExp(r'[（）；・：]| · '),
      onMatch: (m) => m[0] == '：' ? ': ' : m[0]!,
      onNonMatch: (piece) {
        final e = uiCatalog[piece.trim()];
        if (e == null) return piece;
        changed = true;
        return language == 'fr' ? e.$2 : e.$1;
      });
  return changed ? out : null;
}

// Anchored templates preserve interpolated values verbatim: names, answers,
// server messages and counts must never be translated by substring replacement.
final _templates = [
  for (final e in _templateCopy.entries)
    _UiTemplate(e.key, e.value.$1, e.value.$2),
];

class _UiTemplate {
  final RegExp pattern;
  final String en;
  final String fr;
  _UiTemplate(String source, this.en, this.fr)
      : pattern = RegExp(
            '^${source.split(RegExp(r'\{\d+\}')).map(RegExp.escape).join('(.*?)')}\$',
            dotAll: true);
}

const _templateCopy = <String, (String, String)>{
  '發音錄音：{0}': ('Recording: {0}', 'Enregistrement : {0}'),
  '已送出 · #{0}': ('Sent · #{0}', 'Envoyé · #{0}'),
  // 問題回報 #728.
  '處理中 · #{0}': ('In progress · #{0}', 'En cours · #{0}'),
  '已處理 · #{0}': ('Done · #{0}', 'Traité · #{0}'),
  // Before the generic 「{0} 張」 below (卡 #496).
  '每天最多 {0} 張新卡': ('Up to {0} new cards a day', 'Jusqu’à {0} nouvelles cartes par jour'),
  '每天最多複習 {0} 張': ('Up to {0} reviews a day', 'Jusqu’à {0} révisions par jour'),
  '辨識單字列表 ({0})': ('Recognised words ({0})', 'Mots reconnus ({0})'),
  'AI 在這張照片找到的字最難到「{0}」，按「重新掃描標籤」請 AI 找更難的字': (
    'The hardest word the AI found here is “{0}”; tap “Rescan labels” for harder words',
    'Le mot le plus difficile trouvé ici est « {0} » ; touchez « Réanalyser » pour en trouver'
  ),
  '這 {0} 個字在詞庫裡還沒有圖片，可以先看單字': (
    'No lexicon pictures for these {0} words yet; here are the words',
    'Pas encore d’images pour ces {0} mots ; voici les mots'
  ),
  '單字集 · {0} 個單字 · {1} 張詞庫圖片': (
    'Word set · {0} words · {1} lexicon pictures',
    'Liste de mots · {0} mots · {1} images'
  ),
  '往前第 {0} 張，已經評分過': (
    '{0} cards back; already graded',
    '{0} cartes en arrière ; déjà notée'
  ),
  '已在這個位置加上「{0}」': ('Added “{0}” here', '« {0} » ajouté ici'),
  '全部加入（{0}）': ('Add all ({0})', 'Tout ajouter ({0})'),
  '已加入 {0} 個單字': ('{0} words added', '{0} mots ajoutés'),
  '顯示更多（{0}）': ('Show more ({0})', 'Afficher plus ({0})'),
  '第 {0} / {1} 張　·　左右滑動換照片': (
    'Photo {0} of {1} · swipe to change photo',
    'Photo {0} sur {1} · balayez pour changer de photo'
  ),
  '最近 7 天（每日）：{0}': (
    'Last 7 days (daily): {0}',
    '7 derniers jours (par jour) : {0}'
  ),
  '最近 4 週（每週）：{0}': (
    'Last 4 weeks (weekly): {0}',
    '4 dernières semaines (par semaine) : {0}'
  ),
  '共 {0} 次複習。': ('{0} reviews in total.', '{0} révisions au total.'),
  '{0}・估': ('{0} · est.', '{0} · est.'),
  '單字難度 {0} · {1}': ('Difficulty: {0} · {1}', 'Difficulté : {0} · {1}'),
  '圖片來源：{0}': ('Photo source: {0}', 'Source de la photo : {0}'),
  '這次複習了 {0} 張卡': ('You reviewed {0} cards', 'Vous avez révisé {0} cartes'),
  // 問題回報 #533 #534 (M214).
  '今天 {0} 張，約 {1} 分鐘。做完還可以繼續練習，想休息時按左上角結束。': (
    '{0} cards today, about {1} min. You can keep practising after; tap the top-left button to stop.',
    '{0} cartes aujourd’hui, env. {1} min. Vous pouvez continuer ensuite ; touchez en haut à gauche pour arrêter.'
  ),
  '約 {0} 分鐘': ('About {0} min', 'Env. {0} min'),
  '已完成 {0} / {1} 張': ('{0} of {1} cards done', '{0} cartes sur {1} faites'),
  '記得 {0} 張・再練 {1} 次': (
    'Remembered {0} · {1} retries',
    'Retenues : {0} · {1} reprises'
  ),
  '查看「{0}」': ('Open “{0}”', 'Ouvrir « {0} »'),
  '穩定度 {0} 天 · 已複習 {1} 次 · 忘記 {2} 次': (
    'Stability: {0} days · {1} reviews · {2} lapses',
    'Stabilité : {0} jours · {1} révisions · {2} oublis'
  ),
  '今天 {0} 張': ('{0} due today', '{0} à réviser aujourd’hui'),
  '作者：{0}': ('Author: {0}', 'Auteur : {0}'),
  '授權：{0}': ('License: {0}', 'Licence : {0}'),
  '{0} 天後複習': ('Review in {0} days', 'Revoir dans {0} jours'),
  '{0} 個月後複習': ('Review in {0} months', 'Revoir dans {0} mois'),
  '{0} 年後複習': ('Review in {0} years', 'Revoir dans {0} ans'),
  '{0} · 即將推出': ('{0} · Coming soon', '{0} · Bientôt'),
  'App 已依你的複習調成 {0}': (
    'The app moved your level to {0} based on your reviews',
    'L’app a réglé votre niveau sur {0} selon vos révisions'
  ),
  '來源：{0}。新照片的單字會以這個程度為中心挑選；照片詳情的難度轉盤只影響那一張照片。': (
    'Source: {0}. New photos use this level; the photo difficulty dial affects only that photo.',
    'Source : {0}. Les nouvelles photos utilisent ce niveau ; le réglage d’une photo ne concerne que celle-ci.'
  ),
  '你最近常把難度調高，要把預設程度改成 {0} 嗎？': (
    'You often increase difficulty. Set the default to {0}?',
    'Vous augmentez souvent la difficulté. Passer au niveau {0} par défaut ?'
  ),
  '你最近常把難度調低，要把預設程度改成 {0} 嗎？': (
    'You often decrease difficulty. Set the default to {0}?',
    'Vous réduisez souvent la difficulté. Passer au niveau {0} par défaut ?'
  ),
  '希望記住的比例 {0}%': ('Desired retention: {0}%', 'Mémorisation souhaitée : {0} %'),
  '上次確認：{0}': ('Last checked: {0}', 'Dernière vérification : {0}'),
  '✓ 已連線 · {0}': ('✓ Connected · {0}', '✓ Connecté · {0}'),
  '⌛ 有 {0} 張照片等待 AI 辨識': (
    '⌛ {0} photos waiting for AI',
    '⌛ {0} photos en attente de l’IA'
  ),
  '⌛ 正在辨識照片（還有 {0} 張在排隊）': (
    '⌛ Recognising photo ({0} waiting)',
    '⌛ Reconnaissance en cours ({0} en attente)'
  ),
  '共 {0} 張圖片 · 每張都有單字標籤': (
    '{0} photos · all with word labels',
    '{0} photos · toutes avec étiquettes'
  ),
  '{0} 筆正式單字 · 與資料庫同步': (
    '{0} published words · synced with database',
    '{0} mots publiés · synchronisés avec le dictionnaire'
  ),
  '{0}：{1} 張圖片有這個程度的標籤 · 不到 {2} 個字的從相近程度補': (
    '{0}: {1} photos with labels at this level · under {2} words filled from nearby levels',
    '{0} : {1} photos avec étiquettes de ce niveau · moins de {2} mots complétés par les niveaux voisins'
  ),
  '{0}：{1} 張圖片有這個程度的標籤 · 不到 {2} 個字的從相近程度補 · {3} 張的搜尋字在其他程度': (
    '{0}: {1} photos with labels at this level · under {2} words filled from nearby levels · {3} match at another level',
    '{0} : {1} photos avec étiquettes de ce niveau · moins de {2} mots complétés par les niveaux voisins · {3} correspondent à un autre niveau'
  ),
  '這個程度不到 {0} 個字，已從相近程度補上': (
    'Fewer than {0} words at this level; filled from nearby levels',
    'Moins de {0} mots à ce niveau ; complété par les niveaux voisins'
  ),
  '搜尋的字 {0} 在 {1}': (
    'Searched word {0} is at {1}',
    'Le mot {0} est au niveau {1}'
  ),
  '搜尋的字 {0} 沒有分級': (
    'Searched word {0} has no level',
    'Le mot {0} n’a pas de niveau'
  ),
  '切到 {0}': ('Switch to {0}', 'Passer à {0}'),
  '包含待補齊單字（{0}）': (
    'Include incomplete words ({0})',
    'Inclure les mots incomplets ({0})'
  ),
  '第 {0} 個，共 {1} 個': ('{0} of {1}', '{0} sur {1}'),
  '找到 {0} 個字': ('Found {0} words', '{0} mots trouvés'),
  '{0} 個單字': ('{0} words', '{0} mots'),
  '{0} 張': ('{0} photos', '{0} photos'),
  // 一次匯入多張照片 (問題回報 #677).
  '存到相片冊（{0} 張）': (
    'Save to album ({0} photos)',
    'Enregistrer dans un album ({0} photos)'
  ),
  '加入 {0} 張': ('Add {0}', 'Ajouter {0}'),
  '已選 {0} 張': ('{0} selected', '{0} sélectionnées'),
  '正在加入第 {0} 張，共 {1} 張': (
    'Adding photo {0} of {1}',
    'Ajout de la photo {0} sur {1}'
  ),
  '已加入 {0} 張照片，AI 會一張一張辨識': (
    '{0} photos added; the AI will recognize them one by one',
    '{0} photos ajoutées ; l’IA les reconnaîtra une par une'
  ),
  '已加入 {0} 張照片，AI 會一張一張辨識（{1} 張已加入過，略過）': (
    '{0} photos added; the AI will recognize them one by one ({1} already added, skipped)',
    '{0} photos ajoutées ; l’IA les reconnaîtra une par une ({1} déjà ajoutées, ignorées)'
  ),
  '資料庫圖片（{0}）': ('Database photos ({0})', 'Photos du dictionnaire ({0})'),
  '出現這個單字的照片（{0}）': ('Photos with this word ({0})', 'Photos avec ce mot ({0})'),
  '展開全部（{0}）': ('Show all ({0})', 'Tout afficher ({0})'),
  '你的答案：{0}': ('Your answer: {0}', 'Votre réponse : {0}'),
  '正確答案：{0}': ('Correct answer: {0}', 'Bonne réponse : {0}'),
  '聽 {0} 的發音': ('Listen to {0}', 'Écouter {0}'),
  '復原 {0}': ('Restore {0}', 'Rétablir {0}'),
  '開啟照片「{0}」': ('Open photo “{0}”', 'Ouvrir la photo « {0} »'),
  '沒有相機或相簿權限，請到手機設定開啟後再試。': (
    'No camera or photo permission. Turn it on in Settings and try again.',
    'Autorisation caméra ou photos manquante. Activez-la dans Réglages puis réessayez.'
  ),
  '手機儲存空間不足，請清出空間後再試。': (
    'Not enough storage. Free up some space and try again.',
    'Espace insuffisant. Libérez de l’espace puis réessayez.'
  ),
  '這張照片的格式無法使用，請換一張。': (
    'This photo format can’t be used. Please pick another.',
    'Ce format de photo n’est pas pris en charge. Choisissez-en une autre.'
  ),
  '發生問題，請再試一次。': (
    'Something went wrong. Please try again.',
    'Un problème est survenu. Réessayez.'
  ),
  '拍照失敗：{0}': ('Could not take photo: {0}', 'Échec de la prise de photo : {0}'),
  '儲存照片失敗：{0}': (
    'Could not save photo: {0}',
    'Échec de l’enregistrement : {0}'
  ),
  '無法開啟相簿：{0}': (
    'Could not open gallery: {0}',
    'Impossible d’ouvrir la galerie : {0}'
  ),
  '照片中：{0}': ('In the photo: {0}', 'Sur la photo : {0}'),
  '待補：{0}': ('Pending: {0}', 'En attente : {0}'),
  // The longer one first: templates match in order.
  '詞庫已更新：{0} 個字補上{1}，查看是哪些字': (
    'Dictionary updated: {1} added for {0} words, see which ones',
    'Dictionnaire mis à jour : {1} ajouté(s) pour {0} mots, voir lesquels'
  ),
  '詞庫已更新：{0} 個字補上{1}': (
    'Dictionary updated: {1} added for {0} words',
    'Dictionnaire mis à jour : {1} ajouté(s) pour {0} mots'
  ),
  '補上：{0}': ('Added: {0}', 'Ajouté : {0}'),
  '尚缺：{0}。詞庫更新後會自動補上。': (
    'Missing: {0}. Added automatically after a dictionary update.',
    'Manquant : {0}. Ajout automatique après une mise à jour.'
  ),
  'AI 打標籤：{0}': ('AI labelling: {0}', 'Étiquetage IA : {0}'),
  '已新增「{0}」，例句與翻譯會在背景補上。': (
    'Added “{0}”; examples and translations will follow.',
    '« {0} » ajouté ; exemples et traductions suivront.'
  ),
  // 問題回報 #301：一字一卡，「張卡片」和「個單字」重複，拿掉
  '{0}：{1} 個單字 · {2} 張照片 · 已學會 {3} 個': (
    '{0}: {1} words · {2} photos · {3} learned',
    '{0} : {1} mots · {2} photos · {3} acquis'
  ),
  // 匯出到 Anki (問題回報 #325)
  '匯出到 Anki': ('Export to Anki', 'Exporter vers Anki'),
  '匯出到 Anki：選擇範圍': (
    'Export to Anki: choose what',
    'Exporter vers Anki : choisir'
  ),
  '正在建立 Anki 匯入檔…': ('Creating the Anki file…', 'Création du fichier Anki…'),
  '把單字卡連同照片和發音存成 Anki 檔，可以存到檔案或傳到其他 App。': (
    'Saves your word cards with photos and pronunciation as an Anki file you can save to Files or send to another app.',
    'Enregistre vos cartes avec photos et prononciation dans un fichier Anki, à garder dans Fichiers ou envoyer à une autre app.'
  ),
  '這個範圍沒有單字可以匯出': ('No words to export here', 'Aucun mot à exporter ici'),
  // 備份與還原 (問題回報 #278)
  '匯出備份': ('Export backup', 'Exporter une sauvegarde'),
  '從備份還原': ('Restore from backup', 'Restaurer une sauvegarde'),
  '從備份還原？': ('Restore from backup?', 'Restaurer une sauvegarde ?'),
  '選擇備份檔': ('Choose backup file', 'Choisir le fichier'),
  '正在建立備份…': ('Creating backup…', 'Création de la sauvegarde…'),
  '正在還原…': ('Restoring…', 'Restauration…'),
  '還原會用備份檔取代目前所有的單字、照片、相片冊、複習紀錄與設定。想保留目前的資料，請先匯出備份。': (
    'Restoring replaces all your current words, photos, albums, review history and settings with the backup. To keep your current data, export a backup first.',
    'La restauration remplace tous vos mots, photos, albums, historique de révision et réglages actuels. Pour garder vos données actuelles, exportez d’abord une sauvegarde.'
  ),
  '備份檔包含單字、照片、相片冊、複習紀錄與設定。': (
    'A backup holds your words, photos, albums, review history and settings.',
    'Une sauvegarde contient vos mots, photos, albums, historique de révision et réglages.'
  ),
  '金鑰不會存進備份檔；在新手機還原備份後要重新輸入。': (
    'The key is not saved in backups; enter it again after restoring on a new phone.',
    'La clé n’est pas enregistrée dans les sauvegardes ; saisissez-la à nouveau après une restauration sur un nouveau téléphone.'
  ),
  '這不是拍照學單字的備份檔': (
    'This is not a 拍照學單字 backup file',
    'Ce fichier n’est pas une sauvegarde de 拍照學單字'
  ),
  '這個備份來自較新版本的 App，請先更新 App 再還原': (
    'This backup comes from a newer version of the app. Update the app, then restore.',
    'Cette sauvegarde vient d’une version plus récente de l’app. Mettez l’app à jour, puis restaurez.'
  ),
  '備份檔已損壞，無法讀取': (
    'The backup file is damaged and cannot be read',
    'Le fichier de sauvegarde est endommagé'
  ),
  '備份檔不完整，可能沒有存完': (
    'The backup file is incomplete; it may not have finished saving',
    'Le fichier de sauvegarde est incomplet'
  ),
  '已建立備份：{0} 個單字、{1} 張照片、{2} 筆複習紀錄（照片 {3}）': (
    'Backup created: {0} words, {1} photos, {2} reviews (photos {3})',
    'Sauvegarde créée : {0} mots, {1} photos, {2} révisions (photos {3})'
  ),
  '已還原：{0} 個單字、{1} 張照片、{2} 筆複習紀錄': (
    'Restored: {0} words, {1} photos, {2} reviews',
    'Restauré : {0} mots, {1} photos, {2} révisions'
  ),
  // 卡 #496 (問題回報 #494): toasts and counts a French learner still saw in
  // Chinese. Kept last so the longer 來源：… template above wins.
  '已刪除「{0}」，這張照片不會再推薦它': (
    'Deleted “{0}”; this photo won’t suggest it again',
    '« {0} » supprimé ; cette photo ne le proposera plus'
  ),
  '已把「{0}」移到已學會': ('Moved “{0}” to Learned', '« {0} » déplacé dans Appris'),
  '已復原「{0}」': ('Restored “{0}”', '« {0} » restauré'),
  '在照片上點一下，放「{0}」的位置': (
    'Tap the photo where “{0}” goes',
    'Touchez la photo à l’endroit de « {0} »'
  ),
  '已移除「{0}」，可在單字本復原': (
    'Removed “{0}”; restore it from My words',
    '« {0} » retiré ; restaurez-le depuis Mes mots'
  ),
  '移除「{0}」？': ('Remove “{0}”?', 'Retirer « {0} » ?'),
  '{0} 張辨識失敗，可在相片頁重試': (
    '{0} photos failed; retry from the photo page',
    '{0} photos ont échoué ; réessayez depuis la page photo'
  ),
  '第 {0} 張，共 {1} 張，左右滑動切換照片': (
    'Photo {0} of {1}; swipe to change photo',
    'Photo {0} sur {1} ; balayez pour changer de photo'
  ),
  '匯出失敗：{0}': ('Export failed: {0}', 'Échec de l’export : {0}'),
  '備份失敗：{0}': ('Backup failed: {0}', 'Échec de la sauvegarde : {0}'),
  '還原失敗：{0}': ('Restore failed: {0}', 'Échec de la restauration : {0}'),
  '來源：{0}': ('Source: {0}', 'Source : {0}'),
  // M180 (owner #732): the photo's 詞性 × CEFR table.
  '已加入「{0}」': ('Added “{0}”', '« {0} » ajouté'),
};
