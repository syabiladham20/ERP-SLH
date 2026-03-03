import re

files_to_modify = [
    'templates/flock_detail.html',
    'templates/flock_detail_readonly.html',
    'templates/flock_detail_modern.html'
]

js_code = """
// --- Floating Notes Logic ---
let activeAddNoteChart = null;
let allFloatingNotes = [];

function toggleAddNoteMode(chartId) {
    if (activeAddNoteChart === chartId) {
        activeAddNoteChart = null;
        // Reset button
        document.querySelectorAll('button[onclick="toggleAddNoteMode(\\'' + chartId + '\\')"]').forEach(btn => {
            btn.classList.remove('btn-primary');
            btn.classList.add('btn-outline-secondary');
        });
    } else {
        if (activeAddNoteChart) {
            document.querySelectorAll('button[onclick="toggleAddNoteMode(\\'' + activeAddNoteChart + '\\')"]').forEach(btn => {
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-outline-secondary');
            });
        }
        activeAddNoteChart = chartId;
        document.querySelectorAll('button[onclick="toggleAddNoteMode(\\'' + chartId + '\\')"]').forEach(btn => {
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary');
        });
    }
}

const floatingNotePlugin = {
    id: 'floatingNoteInteraction',
    afterEvent(chart, args) {
        if (args.event.type === 'click') {
            const chartId = chart.canvas.id;
            if (activeAddNoteChart === chartId) {
                const xVal = chart.scales.x.getValueForPixel(args.event.x);
                const yVal = chart.scales.y.getValueForPixel(args.event.y);

                // Get categorical label from x-axis index
                let xLabel = xVal;
                if (chart.data.labels && chart.data.labels[xVal]) {
                    xLabel = chart.data.labels[xVal];
                }

                toggleAddNoteMode(chartId); // turn off mode

                const noteText = prompt("Enter note text:");
                if (noteText && noteText.trim() !== '') {
                    const payload = {
                        flock_id: {{ flock.id }},
                        chart_id: chartId,
                        x_value: String(xLabel),
                        y_value: yVal,
                        content: noteText.trim()
                    };

                    fetch('/api/floating_notes', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (res.success) {
                            payload.id = res.id;
                            allFloatingNotes.push(payload);
                            updateChartAnnotations(chart);
                        } else {
                            alert("Failed to save note: " + res.error);
                        }
                    });
                }
            }
        }
    }
};

Chart.register(floatingNotePlugin);

function updateChartAnnotations(chart) {
    if (!chart) return;
    const chartId = chart.canvas.id;
    const chartNotes = allFloatingNotes.filter(n => n.chart_id === chartId);

    if (!chart.options.plugins) chart.options.plugins = {};
    if (!chart.options.plugins.annotation) chart.options.plugins.annotation = {};
    if (!chart.options.plugins.annotation.annotations) chart.options.plugins.annotation.annotations = {};

    // Preserve non-note annotations if any (e.g., target lines)
    const newAnnotations = {};
    for (const [key, ann] of Object.entries(chart.options.plugins.annotation.annotations)) {
        if (!key.startsWith('note_')) {
            newAnnotations[key] = ann;
        }
    }

    chartNotes.forEach(note => {
        newAnnotations['note_' + note.id] = {
            type: 'label',
            xValue: note.x_value,
            yValue: note.y_value,
            content: note.content,
            backgroundColor: 'rgba(255, 255, 255, 0.9)',
            color: 'black',
            borderWidth: 1,
            borderColor: '#ccc',
            borderRadius: 4,
            padding: 4,
            font: { size: 12 },
            click: function({chart, element}) {
                if (activeAddNoteChart) return; // don't delete if trying to add
                if (confirm('Delete this note: "' + note.content + '"?')) {
                    fetch('/api/floating_notes/' + note.id, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(res => {
                        if (res.success) {
                            allFloatingNotes = allFloatingNotes.filter(n => n.id !== note.id);
                            updateChartAnnotations(chart);
                        } else {
                            alert("Failed to delete note.");
                        }
                    });
                }
            }
        };
    });

    chart.options.plugins.annotation.annotations = newAnnotations;
    chart.update();
}

function fetchAndApplyFloatingNotes() {
    fetch('/api/floating_notes/{{ flock.id }}')
    .then(r => r.json())
    .then(data => {
        allFloatingNotes = data;
        // update all active chart instances
        // assuming charts are accessible globally like generalChart, waterChart, etc.
        const chartsToUpdate = [
            typeof generalChart !== 'undefined' ? generalChart : null,
            typeof waterChart !== 'undefined' ? waterChart : null,
            typeof feedChart !== 'undefined' ? feedChart : null,
            typeof maleChart !== 'undefined' ? maleChart : null,
            typeof femaleChart !== 'undefined' ? femaleChart : null,
            typeof hatchingEggChart !== 'undefined' ? hatchingEggChart : null,
            typeof targetChart !== 'undefined' ? targetChart : null,
            typeof hatchChart !== 'undefined' ? hatchChart : null
        ];

        chartsToUpdate.forEach(c => {
            if (c) updateChartAnnotations(c);
        });
    });
}

// Call on load
document.addEventListener('DOMContentLoaded', () => {
    // some charts might initialize after DOMContentLoaded, we can set a timeout or rely on specific lifecycle
    setTimeout(fetchAndApplyFloatingNotes, 1000);
});
"""

for filename in files_to_modify:
    with open(filename, 'r') as f:
        content = f.read()

    if "toggleAddNoteMode" not in content and "// --- Floating Notes Logic ---" not in content:
        # append just before the closing script tag
        content = content.replace("</script>\n{% endblock %}", js_code + "\n</script>\n{% endblock %}")
        with open(filename, 'w') as f:
            f.write(content)
        print(f"Added JS to {filename}")
    elif "// --- Floating Notes Logic ---" not in content:
        # replace just before closing script tag
        content = content.replace("</script>\n{% endblock %}", js_code + "\n</script>\n{% endblock %}")
        with open(filename, 'w') as f:
            f.write(content)
        print(f"Added JS to {filename}")
