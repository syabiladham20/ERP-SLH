import py_compile
import sys

try:
    with open('app/templates/index_modern.html', 'r', encoding='utf-8') as f:
        pass
    print("Template can be read as UTF-8.")
except Exception as e:
    print("Error reading template:", e)

# Templates shouldn't be compiled as python source code using py_compile anyway
