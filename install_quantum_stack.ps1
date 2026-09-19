$ErrorActionPreference = 'Stop'

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-qiskit.txt

python -c "from qiskit import QuantumCircuit; from qiskit_aer import AerSimulator; from qiskit_optimization import QuadraticProgram; from qiskit_algorithms import QAOA; print('Qiskit quantum stack OK')"

Write-Host 'Installed:'
python -m pip show qiskit qiskit-aer qiskit-optimization qiskit-algorithms | Select-String '^(Name|Version):'
Write-Host 'No additional environment variables are required for Qiskit or Aer.'
