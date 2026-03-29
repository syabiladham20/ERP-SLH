import re

files_to_patch = [
    'templates/bodyweight.html',
    'templates/post_mortem.html',
    'templates/health_log_medication.html'
]

js_code = """
<script>
    document.addEventListener("DOMContentLoaded", function() {
        // Read the 'tab' URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const activeTab = urlParams.get('tab');

        if (activeTab) {
            // Find the tab link corresponding to this tab ID
            const tabLink = document.querySelector(`a[href="#${activeTab}"]`);
            if (tabLink) {
                // Activate using Bootstrap Tab API
                const tab = new bootstrap.Tab(tabLink);
                tab.show();
            }
        }

        // Listen for tab changes and update the URL without refreshing
        const tabElms = document.querySelectorAll('a[data-bs-toggle="tab"]');
        tabElms.forEach(function(tabEl) {
            tabEl.addEventListener('shown.bs.tab', function (event) {
                const targetId = event.target.getAttribute("href").replace("#", "");
                const newUrl = new URL(window.location);
                newUrl.searchParams.set("tab", targetId);
                window.history.replaceState({}, "", newUrl);
            });
        });
    });
</script>
"""

for filepath in files_to_patch:
    with open(filepath, 'r') as f:
        content = f.read()

    # We append it right before the last {% endblock %}
    if "{% endblock %}" in content:
        # split by last occurrence
        parts = content.rsplit("{% endblock %}", 1)
        new_content = parts[0] + js_code + "\n{% endblock %}" + parts[1]

        with open(filepath, 'w') as f:
            f.write(new_content)

print("Applied sticky tabs.")
