from typing import Union


def greet_user(name):
    return f"Hello, {name}!"


def calculate_sum(a, b):
    return a + b


def multiply_numbers(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    return a * b