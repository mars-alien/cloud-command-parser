"""Training / inference text format shared by training, evaluation and the service."""


def build_prompt(text: str) -> str:
    return f"Command: {text}\nJSON:"


def build_example(text: str, target_json: str) -> str:
    return f"{build_prompt(text)} {target_json}"
