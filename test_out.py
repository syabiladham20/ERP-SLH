import subprocess
out = subprocess.check_output(['python3', 'run_tests.py'], stderr=subprocess.STDOUT)
print(out.decode())
