with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start = content.find('afterBody: function(context) {')
end = content.find('  };\n\n  // Data from backend', start)
print(content[start:end])
