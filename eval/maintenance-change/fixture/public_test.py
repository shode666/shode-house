import labels


def test_machine_key_is_stable():
    assert labels.STABLE_KEY == "account_status"
