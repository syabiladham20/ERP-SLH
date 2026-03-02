import re
with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# The user asked: "add standard hatchability % in fertility and hatchability if not yet added"
# It is already added:
# {
#     label: 'Std Hatchability %',
#     data: dStdHatch,
#     ...
# }
# But we should ensure the labels logic properly handles it. We already set global logic to ignore "std".
# Wait, what if `dStdHatch` has no data?
# Let's check how `std_hatch` is assigned.
start = content.find("std_hatch: r.std_hatch")
print(start)
