import re

def insert_datalabels_defaults(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    new_defaults = """  Chart.defaults.set('plugins.datalabels', {
    display: true,
    font: { size: 10 },
    formatter: Math.round
  });
  if (Chart.defaults.datasets.line) {
      Chart.defaults.datasets.line.datalabels = { align: 'top', anchor: 'end' };
  }
  if (Chart.defaults.datasets.bar) {
      Chart.defaults.datasets.bar.datalabels = { align: 'top', anchor: 'end' };
  }
"""

    # insert before "if (Chart.defaults.datasets.line) Chart.defaults.datasets.line.clip = true;"
    content = content.replace("  // Fix for zoom clipping", new_defaults + "  // Fix for zoom clipping")

    with open(filepath, 'w') as f:
        f.write(content)

insert_datalabels_defaults('templates/flock_detail.html')
insert_datalabels_defaults('templates/flock_detail_readonly.html')
