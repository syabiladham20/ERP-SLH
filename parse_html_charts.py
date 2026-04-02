import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# I need to extract the HTML layout for the charts tab.
# `<!-- Charts Tab (Pane 3) -->` to `<!-- Production Summary Tab (Pane 4) -->`
start_charts = content.find('<!-- Charts Tab (Pane 3) -->')
end_charts = content.find('<!-- Production Summary Tab (Pane 4) -->')

charts_html = content[start_charts:end_charts]

# And the modals: `<!-- Floating Note Modal -->` or `<!-- Note Modal -->`
start_note_modal = content.find('<!-- Note Modal -->')
if start_note_modal == -1:
    start_note_modal = content.find('<div class="modal fade" id="noteModal"')

end_note_modal = content.find('</div>', content.find('</div>', content.find('</div>', content.find('</div>', start_note_modal)+1)+1)+1) + 6

# Wait, `flock_detail.html` is the only one I need to base the partial off,
# then I can inject the partial into all 3.
# But what if there are slight styling differences?
# Let's inspect `flock_detail_modern.html` to see if its chart HTML is exactly the same.
