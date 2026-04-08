import sys

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    target_str = """          onClick: (e, elements) => {
              if (elements.length) {
                  const clinicalNotesDatasetIndex = generalChart.data.datasets.findIndex(ds => ds.label === 'Clinical Notes');
                  const notePoint = elements.find(p => p.datasetIndex === clinicalNotesDatasetIndex);
                  if (notePoint) {
                      const rawData = generalChart.data.datasets[notePoint.datasetIndex].data[notePoint.index];
                      if (rawData && (rawData.note || rawData.main_note)) {
                          showNoteModal(rawData);
                      }
                  }
              }
          }"""

    replacement_str = """          onClick: (e, elements) => {
              // GATE 1: Check the physical state of the radio buttons
              const activeMode = document.querySelector('input[name="chartMode"]:checked');

              // If no radio button is found, or if it's not the Daily mode, exit silently
              if (!activeMode || activeMode.id !== 'modeDaily') {
                  return;
              }

              if (elements.length) {
                  const clinicalNotesDatasetIndex = generalChart.data.datasets.findIndex(ds => ds.label === 'Clinical Notes');
                  const notePoint = elements.find(p => p.datasetIndex === clinicalNotesDatasetIndex);
                  if (notePoint) {
                      const rawData = generalChart.data.datasets[notePoint.datasetIndex].data[notePoint.index];
                      // GATE 2 & 3: Defensive data checking
                      if (rawData && typeof rawData === 'object' && (rawData.note || rawData.main_note)) {
                          showNoteModal(rawData);
                      }
                  }
              }
          }"""

    if target_str in content:
        content = content.replace(target_str, replacement_str)
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Patched {filepath}")
    else:
        print(f"Target string not found in {filepath}")

patch_file('templates/flock_detail.html')
