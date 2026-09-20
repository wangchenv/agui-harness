"""Synthetic evaluator demonstration. This module never calls a real model."""
EXECUTION_MODE = 'offline'


def predict(value, *, model, timeout_s):
    return {'output': {'people': value['people'], 'duration_minutes': value['duration_minutes']},
            'model_version': model, 'request_id': 'offline-fixture', 'input_tokens': 10, 'output_tokens': 5}
