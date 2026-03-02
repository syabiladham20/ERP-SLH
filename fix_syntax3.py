with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Fix commonOptions in flock_detail.html
fixed_content = content.replace('''                  afterBody: function(context) {
                      const noteItem = context.find(i => i.dataset.label === 'Clinical Notes');
                      if (noteItem && noteItem.raw && noteItem.raw.note) {
                          return '\\nNote: ' + noteItem.raw.note;
                          }
                      }
                  }
              }
          }
  };''', '''                  afterBody: function(context) {
                      const noteItem = context.find(i => i.dataset.label === 'Clinical Notes');
                      if (noteItem && noteItem.raw && noteItem.raw.note) {
                          return '\\nNote: ' + noteItem.raw.note;
                      }
                      return '';
                  }
              }
          }
      }
  };''')

if fixed_content != content:
    with open('templates/flock_detail.html', 'w') as f:
        f.write(fixed_content)
    print("Fixed syntax in flock_detail.html")
else:
    print("No change needed or couldn't find the exact match.")
