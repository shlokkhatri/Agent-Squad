from main import multiply_numbers


def test_multiply_positive_numbers():
    assert multiply_numbers(2, 3) == 6


def test_multiply_negative_positive_numbers():
    assert multiply_numbers(-2, 3) == -6


def test_multiply_negative_numbers():
    assert multiply_numbers(-2, -3) == 6


def test_multiply_by_zero():
    assert multiply_numbers(5, 0) == 0


def test_zero_multiplication():
    assert multiply_numbers(0, 5) == 0


def test_multiply_floats():
    assert multiply_numbers(2.5, 2) == 5.0


def test_multiply_integer_and_float():
    assert multiply_numbers(10, -0.5) == -5.0