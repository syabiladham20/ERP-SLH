import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# We need to extract everything from the first chart card to the end of the last chart card.
# Looking at the output above, the charts are:
# 1. <div class="card mb-4" id="cardGeneral"> (Assuming this is the ID for general chart based on pattern)
# 2. <div class="card mb-4" id="cardHatching">
# 3. <div class="card mb-4" id="cardWater">
# 4. <div class="card mb-4" id="cardFeed">
# 5. <div class="card mb-4" id="cardMale">
# 6. <div class="card mb-4" id="cardFemale">

match1 = re.search(r'<!-- Production & Mortality Chart -->', content)
match2 = re.search(r'<!-- Eggs HHA -->', content)

if match1 and match2:
    charts_html = content[match1.start():match2.start()]
    print("Found charts section.")
    with open('charts_section.html', 'w') as out:
        out.write(charts_html)
else:
    print("Could not find delimiters.")
