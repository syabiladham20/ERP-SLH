with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start_scripts = content.find('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
end_scripts = content.find('{% endblock %}')
scripts_html = content[start_scripts:end_scripts]

with open('templates/partials/_chart_module.html', 'w') as f:
    f.write('<!-- Extracted Chart Module -->\n')
    f.write(content[content.find('<!-- Charts Tab (Pane 3) -->'):content.find('<!-- Production Summary Tab (Pane 4) -->')])
    # We should also extract the modal HTML
    modal_start = content.find('<div class="modal fade" id="noteModal"')
    # A modal has many nested divs, we can search for the start of the next modal or `<!-- Floating Note Modal -->`
    next_modal = content.find('<!-- Floating Note Modal -->')
    modal_html = content[modal_start:next_modal]
    f.write(modal_html)
    f.write(scripts_html)
