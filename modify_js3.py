import re

files_to_modify = [
    'templates/flock_detail.html',
    'templates/flock_detail_readonly.html',
    'templates/flock_detail_modern.html'
]

replacement_js = """
// --- Floating Notes Logic ---
let activeAddNoteChart = null;
let allFloatingNotes = [];

function toggleAddNoteMode(chartId) {
    if (activeAddNoteChart === chartId) {
        activeAddNoteChart = null;
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

                let xLabel = xVal;
                if (chart.data.labels && chart.data.labels[xVal] !== undefined) {
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

    const currentAnns = chart.options.plugins.annotation.annotations;
    const newAnnotations = Array.isArray(currentAnns) ? {} : { ...currentAnns };

    for (const key of Object.keys(newAnnotations)) {
        if (key.startsWith('note_')) {
            delete newAnnotations[key];
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
            borderWidth: 0,
            borderRadius: 4,
            padding: 4,
            font: { size: 12 },
            callout: { display: false },
            click: function(ctx) {
                if (activeAddNoteChart) return;
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
        const chartsToUpdate = [];
        if (typeof generalChart !== 'undefined') chartsToUpdate.push(generalChart);
        if (typeof waterChart !== 'undefined') chartsToUpdate.push(waterChart);
        if (typeof feedChart !== 'undefined') chartsToUpdate.push(feedChart);
        if (typeof maleChart !== 'undefined') chartsToUpdate.push(maleChart);
        if (typeof femaleChart !== 'undefined') chartsToUpdate.push(femaleChart);
        if (typeof hatchingEggChart !== 'undefined') chartsToUpdate.push(hatchingEggChart);
        if (typeof targetChart !== 'undefined') chartsToUpdate.push(targetChart);
        if (typeof hatchChart !== 'undefined') chartsToUpdate.push(hatchChart);

        chartsToUpdate.forEach(c => {
            if (c) updateChartAnnotations(c);
        });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(fetchAndApplyFloatingNotes, 1500);
});
"""

for filename in files_to_modify:
    with open(filename, 'r') as f:
        content = f.read()

    # ensure we only append once
    if "// --- Floating Notes Logic ---" not in content:
        content = content.replace("</script>\n\n{% endblock %}", replacement_js + "\n</script>\n{% endblock %}")
        content = content.replace("</script>\n{% endblock %}", replacement_js + "\n</script>\n{% endblock %}")

    with open(filename, 'w') as f:
        f.write(content)
    print(f"Updated JS in {filename}")
