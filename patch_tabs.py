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

    # If already patched, skip
    if "const activeTab = urlParams.get('tab');" in content:
        continue

    # Inject js_code before the endblock content or at the end of the file
    if "{% endblock %}" in content:
        content = content.replace("{% endblock %}", js_code + "\n{% endblock %}")
    else:
        content += js_code

    with open(filepath, 'w') as f:
        f.write(content)

print("Patched templates for sticky tabs")
