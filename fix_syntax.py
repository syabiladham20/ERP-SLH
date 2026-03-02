with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# I see a missing brace or extra brace in tooltip callbacks afterBody!
# afterBody: function(context) {
#    const noteItem = context.find(i => i.dataset.label === 'Clinical Notes');
#    if (noteItem && noteItem.raw && noteItem.raw.note) {
#        return '\nNote: ' + noteItem.raw.note;
#        }
#    }

print("Looking at afterBody:")
match = content[content.find('afterBody'):content.find('afterBody')+250]
print(match)
