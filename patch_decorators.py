import re

with open('app.py', 'r') as f:
    content = f.read()

# We need to find all routes that have @dept_required but DO NOT have @login_required above them.
# A route looks like:
# @app.route(...)
# @dept_required(...)
# def ...

def add_login_required(match):
    route_decorator = match.group(1)
    dept_decorator = match.group(2)
    return f"{route_decorator}\n@login_required\n{dept_decorator}"

# regex to find @app.route followed by @dept_required without @login_required in between
pattern = re.compile(r"(@app\.route\([^\)]+\)[ \t]*(?:\n[ \t]*@app\.route\([^\)]+\)[ \t]*)*)\n([ \t]*@dept_required\([^\)]+\))")

content = pattern.sub(add_login_required, content)

with open('app.py', 'w') as f:
    f.write(content)
