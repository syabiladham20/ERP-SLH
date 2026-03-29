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

    # Remove all added js blocks first
    block = "\n<script>\n    document.addEventListener(\"DOMContentLoaded\", function() {\n        // Read the 'tab' URL parameter"

    # Split content by the exact script tag start to remove it
    parts = content.split('<script>\n    document.addEventListener("DOMContentLoaded", function() {\n        // Read the \'tab\' URL parameter')

    # Keep the first part, which is original content up to the first injected block
    original_content = parts[0]
    # Re-append any removed {% endblock %} tags if we stripped them accidentally
    if "{% endblock %}" not in original_content and len(parts) > 1:
        # Actually it's simpler to just do string manipulation safely
        pass
