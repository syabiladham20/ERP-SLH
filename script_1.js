
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
