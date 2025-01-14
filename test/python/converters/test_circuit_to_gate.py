# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2019.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Tests for the converters."""

from qiskit import QuantumRegister, QuantumCircuit
from qiskit.circuit import Gate, Qubit
from qiskit.test import QiskitTestCase
from qiskit.exceptions import QiskitError


class TestCircuitToGate(QiskitTestCase):
    """Test QuantumCircuit to Gate"""

    def test_simple_circuit(self):
        """test simple circuit"""
        qr1 = QuantumRegister(4, "qr1")
        qr2 = QuantumRegister(3, "qr2")
        qr3 = QuantumRegister(3, "qr3")
        circ = QuantumCircuit(qr1, qr2, qr3)
        circ.cx(qr1[1], qr2[2])

        gate = circ.to_gate()
        q = QuantumRegister(10, "q")

        self.assertIsInstance(gate, Gate)
        self.assertEqual(gate.definition[0].qubits, (q[1], q[6]))

    def test_circuit_with_registerless_bits(self):
        """Test a circuit with registerless bits can be converted to a gate."""
        qr1 = QuantumRegister(2)
        qubits = [Qubit(), Qubit(), Qubit()]
        qr2 = QuantumRegister(3)
        circ = QuantumCircuit(qr1, qubits, qr2)
        circ.cx(3, 5)

        gate = circ.to_gate()
        self.assertIsInstance(gate, Gate)
        self.assertEqual(gate.num_qubits, len(qr1) + len(qubits) + len(qr2))
        gate_definition = gate.definition
        cx = gate_definition.data[0]
        self.assertEqual(cx.qubits, (gate_definition.qubits[3], gate_definition.qubits[5]))
        self.assertEqual(cx.clbits, ())

    def test_circuit_with_overlapping_registers(self):
        """Test that the conversion works when the given circuit has bits that are contained in more
        than one register."""
        qubits = [Qubit() for _ in [None] * 10]
        qr1 = QuantumRegister(bits=qubits[:6])
        qr2 = QuantumRegister(bits=qubits[4:])
        circ = QuantumCircuit(qubits, qr1, qr2)
        circ.cx(3, 5)

        gate = circ.to_gate()
        self.assertIsInstance(gate, Gate)
        self.assertEqual(gate.num_qubits, len(qubits))
        gate_definition = gate.definition
        cx = gate_definition.data[0]
        self.assertEqual(cx.qubits, (gate_definition.qubits[3], gate_definition.qubits[5]))
        self.assertEqual(cx.clbits, ())

    def test_raises(self):
        """test circuit which can't be converted raises"""
        circ1 = QuantumCircuit(3)
        circ1.x(0)
        circ1.cx(0, 1)
        circ1.barrier()

        circ2 = QuantumCircuit(1, 1)
        circ2.measure(0, 0)

        circ3 = QuantumCircuit(1)
        circ3.x(0)
        circ3.reset(0)

        with self.assertRaises(QiskitError):  # TODO: accept barrier
            circ1.to_gate()

        with self.assertRaises(QiskitError):  # measure and reset are not valid
            circ2.to_gate()

    def test_generated_gate_inverse(self):
        """Test inverse of generated gate works."""
        qr1 = QuantumRegister(2, "qr1")
        circ = QuantumCircuit(qr1)
        circ.cx(qr1[1], qr1[0])

        gate = circ.to_gate()
        out_gate = gate.inverse()
        self.assertIsInstance(out_gate, Gate)

    def test_to_gate_label(self):
        """Test label setting."""
        qr1 = QuantumRegister(2, "qr1")
        circ = QuantumCircuit(qr1, name="a circuit name")
        circ.cx(qr1[1], qr1[0])
        gate = circ.to_gate(label="a label")

        self.assertEqual(gate.label, "a label")
