import ast
with open("app.py", "r") as f:
    try:
        ast.parse(f.read())
        print("Syntax OK")
    except SyntaxError as e:
        print(f"Syntax error: {e}")
