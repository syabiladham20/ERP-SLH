with open("templates/bodyweight.html", "r") as f:
    content = f.read()

content = content.replace("log.date.strftime('%Y-%m-%d')", "log.date")

with open("templates/bodyweight.html", "w") as f:
    f.write(content)
