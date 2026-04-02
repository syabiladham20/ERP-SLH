with open('templates/flock_detail.html', 'r') as f:
    fd_content = f.read()

with open('templates/flock_detail_modern.html', 'r') as f:
    fdm_content = f.read()

start_fd = fd_content.find('<!-- Charts Tab (Pane 3) -->')
end_fd = fd_content.find('<!-- Production Summary Tab (Pane 4) -->')
fd_charts = fd_content[start_fd:end_fd]

start_fdm = fdm_content.find('<!-- Charts Tab (Pane 3) -->')
end_fdm = fdm_content.find('<!-- Production Summary Tab (Pane 4) -->')
fdm_charts = fdm_content[start_fdm:end_fdm]

print("Diff lengths:", len(fd_charts), len(fdm_charts))
