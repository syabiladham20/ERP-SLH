import json

data = {
    'dates': ['2026-02-01', '2026-02-02', '2026-02-03', '2026-02-04'],
    'medication_active': [1, 1, 1, None],
    'medication_names': [['Med A', 'Med B'], ['Med A', 'Med B'], ['Med A', 'Med B'], []]
}

print(json.dumps(data))
