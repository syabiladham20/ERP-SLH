import re

with open('templates/index_modern.html', 'r') as f:
    content = f.read()

target = """            <form action="{{ url_for('toggle_prelay', id=flock.id) }}" method="POST" style="display: inline;">
                <button type="submit" class="btn btn-link text-warning text-sm mb-0 px-0 ms-2" onclick="return confirm('Change phase for {{ flock.flock_id }}?');">
                    Switch to {% if flock.phase in ['Brooding', 'Growing'] %}Production{% else %}Rearing{% endif %}
                </button>
            </form>"""

replacement = """            <form action="{{ url_for('toggle_prelay', id=flock.id) }}" method="POST" style="display: inline;">
                {% if flock.phase in ['Pre-lay', 'Production'] %}
                  <input type="hidden" name="revert" value="true">
                {% endif %}
                <button type="submit" class="btn btn-link text-warning text-sm mb-0 px-0 ms-2" onclick="return confirm('Change phase for {{ flock.flock_id }}?');">
                    Switch to {% if flock.phase in ['Brooding', 'Growing'] %}Pre-lay{% else %}Brooding{% endif %}
                </button>
            </form>"""

content = content.replace(target, replacement)
with open('templates/index_modern.html', 'w') as f:
    f.write(content)
