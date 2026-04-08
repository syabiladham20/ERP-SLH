def fix_modals(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # It looks like the modal is duplicated or something. Let me just remove everything below `{% endblock %}`
    # Wait, the `{% block modals %}` was not removed properly.
    # The actual modal `noteModal` is now in `_chart_module.html`. We don't want it here.
    # Also there are multiple `{% endblock %}`.

    # Let's clean up the end of the file.

    start_content_endblock = content.find('{% endblock %}')

    # Actually, the original file had:
    # {% endblock %} (for content)
    # {% block modals %}
    # <div class="modal fade" id="noteModal"...
    # ...
    # {% endblock %}

    # I replaced all scripts with the include.

    # So I should just make sure the file ends nicely.

    # Re-reading the `flock_detail.html`:
    idx1 = content.find('{% endblock %}\n\n{% block modals %}')

    if idx1 != -1:
        content = content[:idx1+len('{% endblock %}\n\n{% block modals %}')] + '\n\n{% endblock %}\n'

    with open(filepath, 'w') as f:
        f.write(content)

fix_modals('templates/flock_detail.html')
fix_modals('templates/flock_detail_modern.html')
fix_modals('templates/flock_detail_readonly.html')
