

def test_codex_only_cards_are_not_picked_by_claude():
    """Owner 11/27: [上下游檢查] cards go to Codex only until the weekly Claude quota resets (#1464 slipped
    to Claude Code because only the issue swarm checked the rule)."""
    import pick_card as pc
    from datetime import datetime
    caps = pc.load_capabilities()
    board = {'bots': [], 'deck': [{'card': 'task', 'id': 9001, 'kind': 'once', 'status': 'queued',
                                   'title': '問題回報 #1889：[上下游檢查] 批次 00（100 字）', 'difficulty': 3}]}
    before = datetime.fromisoformat('2026-11-28T10:00:00+08:00')
    after = datetime.fromisoformat('2026-12-01T10:00:00+08:00')
    assert not pc.candidates(board, 'Claude Code', caps, state={}, now=before)
    assert pc.candidates(board, 'Codex', caps, state={}, now=before)
    assert pc.candidates(board, 'Claude Code', caps, state={}, now=after)
