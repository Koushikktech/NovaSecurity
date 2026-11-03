from contract import total


def test_regression():
    assert total([]) == 0


def test_happy():
    assert total([2, 3]) == 5
