def fixture_owned_ids(word):
    """Legacy semantic tests explicitly own every word declared in their fixture.

    Ownership exclusions and absent scopes are tested separately without this helper.
    """
    return {word['id'], *(r['target_lexeme_id'] for r in word['relations'])}
