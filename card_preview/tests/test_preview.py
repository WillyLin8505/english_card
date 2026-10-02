"""Synthetic fixtures are confined to tests; the shipped UI has no demo words."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domain import KINDS, default_layout, validate_layout, prepare_exercise, quality, glosses_overlap, merge_usages, plausible_form
from repository import image_allowed
from state import State
from server import PreviewService, make_handler
from http.server import ThreadingHTTPServer


def word(id=1, lemma='apple'):
    return dict(id=id, lemma=lemma, language='en', native_language='zh-TW', pos='noun', cefr='A1', updated_at='2026-09-25T00:00:00Z',
        senses=[dict(id=id, translation='測試義項', definition='test definition')],
        examples=[dict(id=1, sense_id=1, text='An apple is on the table.', translation='測試例句翻譯')],
        relations=[], forms=[], images=[], audio=[], pronunciations=[], etymology=[], provenance=[], fields=[])


def packet(kind='cloze'):
    cards={i:word(i,n) for i,n in enumerate(['apple','book','shoe'],1)}
    bundle=dict(id='test-only',kind=kind,lexeme_id=1,sense_id=1,target_language='en',native_language='zh-TW',
        lexeme_updated_at=cards[1]['updated_at'],example_id=1,answer_form='apple',
        validation=dict(status='approved',reviewer='unit-test',reason='Synthetic test only',checked_at='2026-09-25'),
        options=[dict(lexeme_id=i,sense_id=i,reason='Test explanation',lexeme_updated_at=c['updated_at']) for i,c in cards.items()])
    return cards,bundle


class DomainTests(unittest.TestCase):
    def test_default_layout_valid(self):
        self.assertEqual(validate_layout(default_layout()),default_layout())

    def test_answer_cannot_hide_or_move_front(self):
        for changes in [dict(visible=False),dict(side='front')]:
            layout=default_layout();next(s for s in layout['sections'] if s['key']=='answer').update(changes)
            with self.assertRaises(ValueError):validate_layout(layout)

    def test_photo_and_examples_cannot_leak_front(self):
        for key in ['images','examples','senses','pronunciation']:
            layout=default_layout();next(s for s in layout['sections'] if s['key']==key)['side']='front'
            with self.assertRaises(ValueError):validate_layout(layout)

    def test_limit_and_duplicate_rejected(self):
        layout=default_layout();layout['sections'][0]['limit']=100
        with self.assertRaises(ValueError):validate_layout(layout)
        layout=default_layout();layout['sections'].append(layout['sections'][0])
        with self.assertRaises(ValueError):validate_layout(layout)

    def test_recall_template_removed(self):
        self.assertNotIn('recall',[k['id'] for k in KINDS])

    def test_quality_tracks_each_translation(self):
        w=word();w['senses'].append(dict(id=2,translation=None));w['examples'][0]['translation']=None
        w['relations']=[dict(id=15,target_word='fruit',translation=None)]
        self.assertTrue({'sense:2','example:1','relation:15'}.issubset({r['field'] for r in quality(w)}))

    def test_no_invented_options(self):
        for kind in ['cloze','photo_choice','similar','drag']:
            self.assertFalse(prepare_exercise(word(),kind,1)['available'])

    def test_image_requires_approval_license_and_ready(self):
        valid=dict(review_status='approved',status='ready',path='images/test.jpg',page_url='https://example.com',license_code='CC BY 4.0')
        self.assertTrue(image_allowed(valid))
        for changes in [dict(review_status='pending'),dict(status='blocked'),dict(license_code='CC BY-SA 4.0'),dict(license_code='CC BY-NC 4.0'),dict(path=None)]:
            self.assertFalse(image_allowed({**valid,**changes}))

    def test_photo_recall_requires_same_sense(self):
        w=word();w['images']=[dict(sense_id=2)]
        self.assertFalse(prepare_exercise(w,'photo_recall',1)['available'])
        w['images'][0]['sense_id']=1
        self.assertTrue(prepare_exercise(w,'photo_recall',1)['available'])

    def test_cloze_uses_real_example_and_hides_answer(self):
        cards,bundle=packet();result=prepare_exercise(cards[1],'cloze',1,bundle,cards)
        self.assertTrue(result['available'],result['reasons']);self.assertNotIn('apple',result['prompt'])
        self.assertEqual(len(result['options']),3)

    def test_wrong_language_and_stale_packets_fail(self):
        for patch in [dict(native_language='fr'),dict(lexeme_updated_at='old'),dict(sense_id=99)]:
            cards,bundle=packet();bundle.update(patch)
            self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_stale_option_fails(self):
        cards,bundle=packet();cards[2]['updated_at']='new'
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_duplicate_or_wrong_pos_options_fail(self):
        cards,bundle=packet();cards[2]['pos']='verb'
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])
        cards,bundle=packet();bundle['options'][1]=copy.deepcopy(bundle['options'][0])
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_unreviewed_packet_fails(self):
        cards,bundle=packet();bundle['validation']['status']='pending'
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_multiple_blanks_fail(self):
        cards,bundle=packet();cards[1]['examples'][0]['text']='apple apple'
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_cloze_rejects_answer_hidden_inside_another_word(self):
        cards,bundle=packet();cards[1]['examples'][0]['text']='An apple is not an applecart.'
        self.assertFalse(prepare_exercise(cards[1],'cloze',1,bundle,cards)['available'])

    def test_similar_requires_relations(self):
        cards,bundle=packet('similar')
        for card,meaning in zip(cards.values(),['蘋果','書本','鞋子']):card['senses'][0]['translation']=meaning
        self.assertFalse(prepare_exercise(cards[1],'similar',1,bundle,cards)['available'])
        cards[1]['relations']=[dict(target_lexeme_id=2,relation='related'),dict(target_lexeme_id=3,relation='related')]
        result=prepare_exercise(cards[1],'similar',1,bundle,cards)
        self.assertTrue(result['available'],result['reasons']);self.assertEqual(result['mode'],'match')
        self.assertEqual(sorted(result['native_order']),[1,2,3]);self.assertEqual(sorted(result['target_order']),[1,2,3])

    def test_similar_packet_rejects_overlapping_meanings(self):
        cards,bundle=packet('similar')
        cards[1]['relations']=[dict(target_lexeme_id=2),dict(target_lexeme_id=3)]
        # The fixture gives every option the same gloss, so the pairs cannot be matched uniquely.
        self.assertFalse(prepare_exercise(cards[1],'similar',1,bundle,cards)['available'])

    def test_gloss_overlap(self):
        self.assertTrue(glosses_overlap('慷慨、大方','慷慨'))
        self.assertTrue(glosses_overlap('足夠','足夠的'))
        self.assertFalse(glosses_overlap('大、大型','慷慨、大方'))
        self.assertFalse(glosses_overlap('水果','梨子'))

    def test_drag_validates_boxes(self):
        cards,bundle=packet('drag');bundle['sense_image_id']=10;cards[1]['images']=[dict(sense_id=1,sense_image_id=10)]
        for i,o in enumerate(bundle['options']):o['box']=[i*.25,0,.2,.3]
        self.assertTrue(prepare_exercise(cards[1],'drag',1,bundle,cards)['available'])
        bundle['options'][0]['box']=[.9,0,.2,.3]
        self.assertFalse(prepare_exercise(cards[1],'drag',1,bundle,cards)['available'])

    def test_preview_is_pure(self):
        w=word();before=copy.deepcopy(w)
        quality(w);prepare_exercise(w,'photo_recall',1)
        self.assertEqual(w,before)


class LiveExerciseTests(unittest.TestCase):
    def test_photo_choice_excludes_other_valid_labels_even_under_another_relation(self):
        from domain import live_exercise
        w=word(lemma='dappled');w['senses'][0]['translation']='斑紋的'
        w['images']=[dict(sense_id=1,sense_image_id=10)]
        def rel(id,label,translation,kind):
            return dict(target_lexeme_id=id,target_word=label,translation=translation,
                        relation=kind,pos='adj',cefr='A1',strength=1,detail={})
        w['relations']=[rel(2,'spotted','有斑點的','related'),
                        rel(2,'spotted','有斑點的','synonyms'),
                        rel(3,'mottled','斑駁的','synonyms'),
                        rel(4,'patterned','有圖案的','hypernyms'),
                        rel(5,'marked','斑紋的','related')]
        self.assertFalse(live_exercise(w,'photo_choice',1)['available'])
        w['relations'] += [rel(6,'striped','條紋的','related'),
                           rel(7,'plain','素色的','antonyms')]
        x=live_exercise(w,'photo_choice',1)
        self.assertTrue(x['available'])
        self.assertEqual({o['label'] for o in x['options']},{'dappled','striped','plain'})

    def test_photo_choice_uses_image_and_exactly_three_related_options(self):
        from domain import live_exercise
        w=word();w['images']=[dict(sense_id=1,sense_image_id=10)]
        w['relations']=[
            dict(target_lexeme_id=2,target_word='pear',translation='梨子',relation='related',pos='noun',cefr='A1',strength=.9,detail={}),
            dict(target_lexeme_id=3,target_word='peach',translation='桃子',relation='related',pos='noun',cefr='A1',strength=.8,detail={}),
            dict(target_lexeme_id=4,target_word='rare fruit',translation='罕見水果',relation='related',pos='noun',cefr='C2',strength=.7,detail={'hide_by_default':True})]
        x=live_exercise(w,'photo_choice',1)
        self.assertTrue(x['available']);self.assertEqual(len(x['options']),3)
        self.assertEqual(sum(o['id']==w['id'] for o in x['options']),1)
        self.assertEqual(x['image']['sense_image_id'],10)

    def test_photo_choice_requires_two_usable_distractors(self):
        from domain import live_exercise
        w=word();w['images']=[dict(sense_id=1,sense_image_id=10)]
        w['relations']=[dict(target_lexeme_id=2,target_word='pear',translation='梨子',relation='related',pos='noun',cefr='A1',strength=.9,detail={})]
        self.assertFalse(live_exercise(w,'photo_choice',1)['available'])

    def test_cloze_uses_only_selected_sense_and_real_form(self):
        from domain import live_exercise
        w=word();w['examples']=[dict(id=1,sense_id=1,text='An apple is here.',translation='translation')]
        x=live_exercise(w,'cloze',1)
        self.assertTrue(x['available']);self.assertEqual(x['answer'],'apple')
        self.assertNotIn('apple',x['prompt'])
        self.assertFalse(live_exercise(w,'cloze',2)['available'])
        w['examples'][0]['text']='apple apple'
        self.assertFalse(live_exercise(w,'cloze',1)['available'])

    def test_live_cloze_skips_answer_substring_leaks(self):
        from domain import live_exercise
        w=word();w['examples']=[
            dict(id=1,sense_id=1,text='An apple is not an applecart.',translation='bad'),
            dict(id=2,sense_id=1,text='I ate an apple.',translation='good')]
        x=live_exercise(w,'cloze',1)
        self.assertTrue(x['available']);self.assertEqual(x['example']['id'],2)

    def test_similar_uses_translated_context_and_three_related_options(self):
        from domain import live_exercise
        w=word();w['relations']=[
            dict(target_lexeme_id=2,target_word='fruit',translation='水果、成果',relation='hypernyms',pos='noun',cefr='A1',strength=.9,detail={}),
            dict(target_lexeme_id=5,target_word='produce',translation='成果',relation='related',pos='noun',cefr='A1',strength=.9,detail={}),
            dict(target_lexeme_id=3,target_word='pear',translation='梨子',relation='related',pos='noun',cefr='A1',strength=.8,detail={}),
            dict(target_lexeme_id=4,target_word='apply',translation='應用',relation='similar_spelling',pos='verb',cefr='A2',strength=.8,detail={})]
        x=live_exercise(w,'similar',1)
        self.assertTrue(x['available']);self.assertEqual(x['mode'],'similar_choice')
        self.assertEqual(x['example']['translation'],'測試例句翻譯')
        self.assertNotIn('apple',x['prompt'].casefold())
        labels=[p['label'] for p in x['options']]
        self.assertEqual(sorted(labels),['apple','fruit','pear'])
        self.assertEqual(sum(p['id']==x['correct_id'] for p in x['options']),1)
        w['relations']=w['relations'][:2]
        self.assertFalse(live_exercise(w,'similar',1)['available'])


class MergeUsageTests(unittest.TestCase):
    def test_one_card_per_spelling_keeps_usage_of_each_item(self):
        noun,verb=word(1,'apple'),word(2,'apple');verb['pos']='verb'
        verb['senses']=[dict(id=2,translation='使看似蘋果',definition='v.')]
        verb['examples']=[dict(id=9,sense_id=2,text='Apple it.',translation='測試')]
        noun['forms']=[dict(form='apples',field='plural')];verb['forms']=[dict(form='apples',field='plural'),dict(form='appled',field='past')]
        merged=merge_usages([noun,verb])
        self.assertEqual(merged['id'],1);self.assertEqual([u['pos'] for u in merged['usages']],['noun','verb'])
        self.assertEqual([(s['id'],s['lexeme_id'],s['usage_pos']) for s in merged['senses']],[(1,1,'noun'),(2,2,'verb')])
        self.assertEqual([e['id'] for e in merged['examples']],[1,9])
        self.assertEqual([f['form'] for f in merged['forms']],['apples','appled'])

    def test_merge_does_not_mutate_inputs(self):
        cards=[word(1),word(2)];before=copy.deepcopy(cards)
        merge_usages(cards);self.assertEqual(cards,before)

    def test_examples_require_exact_form_from_the_same_usage(self):
        noun,verb=word(1,'mug'),word(2,'mug');verb['pos']='verb'
        noun['senses']=[dict(id=1,translation='馬克杯',definition='cup')]
        noun['examples']=[dict(id=1,sense_id=1,text='Tom was mugged.',translation='湯姆遭搶。')]
        noun['forms']=[dict(form='mugs',field='noun_plural'),
                       dict(form='meg',field='noun_plural')]
        verb['senses']=[dict(id=2,translation='搶劫',definition='rob')]
        verb['examples']=[dict(id=2,sense_id=2,text='Tom was mugged.',translation='湯姆遭搶。')]
        verb['forms']=[dict(form='mugged',field='verb_past')]
        merged=merge_usages([noun,verb])
        self.assertEqual([e['id'] for e in merged['examples']],[2])
        self.assertEqual([e['id'] for e in merged['rejected_examples']],[1])
        self.assertIn('已從學習卡排除',
                      next(i['message'] for i in quality(merged) if i['field']=='example:1'))

    def test_headword_prefix_is_not_treated_as_a_word_form(self):
        adjective=word(1,'happy');adjective['pos']='adj'
        adjective['examples']=[dict(id=3,sense_id=1,text='Happiness matters.',translation='幸福很重要。')]
        merged=merge_usages([adjective])
        self.assertEqual(merged['examples'],[])
        self.assertEqual([e['id'] for e in merged['rejected_examples']],[3])

    def test_unrelated_source_form_does_not_admit_another_word(self):
        self.assertFalse(plausible_form('pan','pen'))
        self.assertTrue(plausible_form('pan','panned'))
        self.assertTrue(plausible_form('child','children'))


class FakeRepository:
    def entry(self,id,target,native):
        return merge_usages([self.card(id,target,native)])
    def card(self,id,target,native):
        w=word(id);w.update(language=target,native_language=native);return w
    def templates(self,target,native):return []
    def catalog(self):return dict(total=1,pairs=[],languages=[],read_only=True)
    def drag_exercise(self,word,sense):
        return dict(kind='drag',sense_id=sense,available=True,mode='drag',image={'url':'/test.jpg'},options=[])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.state=State(Path(self.temp.name)/'preview.sqlite')
    def tearDown(self):self.temp.cleanup()

    def test_draft_is_pair_isolated_and_publish_immutable(self):
        layout=default_layout();self.state.save('en','zh-TW',layout,True)
        layout['sections'][0]['limit']=2;self.state.save('en','zh-TW',layout)
        data=self.state.templates('en','zh-TW')
        self.assertEqual(data['versions'][0]['layout']['sections'][0]['limit'],1)
        self.assertEqual(data['draft']['sections'][0]['limit'],2)
        self.assertEqual(self.state.templates('en','fr')['versions'],[])

    def test_invalid_publish_does_not_change_state(self):
        layout=default_layout();layout['sections'][0]['limit']=-1
        with self.assertRaises(ValueError):self.state.save('en','zh-TW',layout,True)
        self.assertEqual(self.state.templates('en','zh-TW')['versions'],[])

    def test_named_templates_preserve_legacy_and_isolate_versions(self):
        original = default_layout()
        self.state.save('en', 'zh-TW', original, True)
        one = self.state.create('en', 'zh-TW', '精簡卡')
        two = self.state.create('en', 'zh-TW', '例句卡', original)
        changed = one['draft']
        changed['sections'][0]['limit'] = 2
        self.state.save('en', 'zh-TW', changed, True, one['template_id'])
        self.assertEqual(self.state.templates('en', 'zh-TW')['versions'][0]['layout'], original)
        self.assertEqual(self.state.templates('en', 'zh-TW', two['template_id'])['versions'], [])
        self.assertEqual(self.state.templates('en', 'zh-TW', one['template_id'])['versions'][0]['version'], 1)
        with self.assertRaises(ValueError):
            self.state.templates('en', 'fr', one['template_id'])
        reopened = State(self.state.path)
        self.assertEqual(len(reopened.templates('en', 'zh-TW')['choices']), 3)

    def test_invalid_template_creation_leaves_no_partial_records(self):
        for name, layout in [('', None), ('x' * 81, None), ('broken', {})]:
            with self.assertRaises(ValueError):
                self.state.create('en', 'zh-TW', name, layout)
        self.assertEqual(len(self.state.templates('en', 'zh-TW')['choices']), 1)

    def test_issue_link_and_language_isolation(self):
        self.state.add_issue(dict(lexeme_id=1,target_language='en',native_language='zh-TW',sense_id=1,template='recall',version='draft',field='sense:1',category='翻譯錯誤',note='test'))
        self.assertEqual(len(self.state.issues(1,'en','zh-TW')),1)
        self.assertEqual(self.state.issues(1,'en','fr'),[])

    def test_gets_never_create_preview_metadata(self):
        service=PreviewService(FakeRepository(),self.state)
        for i in range(4):service.card(1,'en','zh-TW');service.templates('en','zh-TW')
        with self.state.connect() as c:
            for table in ['drafts','versions','issues']:
                self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_removed_recall_kind_is_rejected(self):
        service=PreviewService(FakeRepository(),self.state)
        with self.assertRaises(ValueError):service.exercise(service.card(1,'en','zh-TW'),'recall',1)

    def test_drag_without_packet_uses_reviewed_image_tags(self):
        service=PreviewService(FakeRepository(),self.state)
        result=service.exercise(service.card(1,'en','zh-TW'),'drag',1)
        self.assertTrue(result['available']);self.assertEqual(result['mode'],'drag')

    def test_exercise_route_uses_merged_card_example_filter(self):
        class BadFormRepository(FakeRepository):
            def card(self,id,target,native):
                w=word(id,'pan');w.update(language=target,native_language=native)
                w['forms']=[dict(form='pen',field='noun_plural')]
                w['examples']=[dict(id=1,sense_id=1,text='My ballpoint pen is purple.',translation='我的原子筆是紫色的。')]
                return w

        service=PreviewService(BadFormRepository(),self.state)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/exercise/1?target=en&native=zh-TW&kind=cloze&sense=1'
            with urlopen(url) as response: result=json.load(response)
            self.assertFalse(result['available'])
            self.assertIn('尚無包含本詞',result['reasons'][0])
        finally:server.shutdown();server.server_close();thread.join()

    def test_http_api_requires_token_and_rejects_learning_routes(self):
        service=PreviewService(FakeRepository(),self.state)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            req=Request(base+'/api/templates/save',data=json.dumps({'layout':default_layout()}).encode(),headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as error:urlopen(req)
            self.assertEqual(error.exception.code,403)
            error.exception.close()
            req.add_header('X-Preview-Token',service.token)
            with urlopen(req) as r:self.assertEqual(r.status,200)
            bad=Request(base+'/api/reviews',data=b'{}',headers={'Content-Type':'application/json','X-Preview-Token':service.token})
            with self.assertRaises(HTTPError) as error:urlopen(bad)
            self.assertEqual(error.exception.code,404)
            error.exception.close()
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
