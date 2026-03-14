import re
import os

files_to_patch = [
    'templates/index.html',
    'templates/index_modern.html',
    'templates/executive_dashboard.html',
    'templates/executive_dashboard_modern.html',
    'templates/flock_detail.html',
    'templates/flock_detail_modern.html',
    'templates/flock_detail_readonly.html'
]

for fpath in files_to_patch:
    with open(fpath, 'r') as f:
        content = f.read()

    # JS 'Rearing' checks
    content = content.replace("const isRearing = (flockPhase === 'Brooding' || flockPhase === 'Growing');", "const isRearing = (flockPhase === 'Brooding' || flockPhase === 'Growing' || flockPhase === 'Pre-lay');")

    # Text 'Rearing Mort %' checks
    content = content.replace("Brooding/Growing Mort %", "Rearing Mort %")

    # Phase mapping array changes
    content = content.replace("flock.calculated_phase in ['Brooding', 'Growing']", "flock.calculated_phase in ['Brooding', 'Growing', 'Pre-lay']")
    content = content.replace("flock.calculated_phase in ['Pre-lay', 'Production']", "flock.calculated_phase == 'Production'")

    with open(fpath, 'w') as f:
        f.write(content)
