# This code is part of Qiskit.
#
# (C) Copyright IBM 2022.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

# pylint: disable=invalid-name

"""Common preset passmanager generators."""

from typing import Optional

from qiskit.circuit.equivalence_library import SessionEquivalenceLibrary as sel

from qiskit.transpiler.passmanager import PassManager
from qiskit.transpiler.passes import Unroller
from qiskit.transpiler.passes import BasisTranslator
from qiskit.transpiler.passes import UnrollCustomDefinitions
from qiskit.transpiler.passes import Unroll3qOrMore
from qiskit.transpiler.passes import Collect2qBlocks
from qiskit.transpiler.passes import Collect1qRuns
from qiskit.transpiler.passes import ConsolidateBlocks
from qiskit.transpiler.passes import UnitarySynthesis
from qiskit.transpiler.passes import HighLevelSynthesis
from qiskit.transpiler.passes import CheckMap
from qiskit.transpiler.passes import GateDirection
from qiskit.transpiler.passes import BarrierBeforeFinalMeasurements
from qiskit.transpiler.passes import CheckGateDirection
from qiskit.transpiler.passes import TimeUnitConversion
from qiskit.transpiler.passes import ALAPScheduleAnalysis
from qiskit.transpiler.passes import ASAPScheduleAnalysis
from qiskit.transpiler.passes import FullAncillaAllocation
from qiskit.transpiler.passes import EnlargeWithAncilla
from qiskit.transpiler.passes import ApplyLayout
from qiskit.transpiler.passes import RemoveResetInZeroState
from qiskit.transpiler.passes import ValidatePulseGates
from qiskit.transpiler.passes import PadDelay
from qiskit.transpiler.passes import InstructionDurationCheck
from qiskit.transpiler.passes import ConstrainedReschedule
from qiskit.transpiler.passes import PulseGates
from qiskit.transpiler.passes import ContainsInstruction
from qiskit.transpiler.passes import VF2PostLayout
from qiskit.transpiler.passes.layout.vf2_layout import VF2LayoutStopReason
from qiskit.transpiler.passes.layout.vf2_post_layout import VF2PostLayoutStopReason
from qiskit.transpiler.exceptions import TranspilerError
from qiskit.transpiler.layout import Layout


def generate_unroll_3q(
    target,
    basis_gates=None,
    approximation_degree=None,
    unitary_synthesis_method="default",
    unitary_synthesis_plugin_config=None,
):
    """Generate an unroll >3q :class:`~qiskit.transpiler.PassManager`

    Args:
        target (Target): the :class:`~.Target` object representing the backend
        basis_gates (list): A list of str gate names that represent the basis
            gates on the backend target
        approximation_degree (float): The heuristic approximation degree to
            use. Can be between 0 and 1.
        unitary_synthesis_method (str): The unitary synthesis method to use
        unitary_synthesis_plugin_config (dict): The optional dictionary plugin
            configuration, this is plugin specific refer to the specified plugin's
            documenation for how to use.

    Returns:
        PassManager: The unroll 3q or more pass manager
    """
    unroll_3q = PassManager()
    unroll_3q.append(
        UnitarySynthesis(
            basis_gates,
            approximation_degree=approximation_degree,
            method=unitary_synthesis_method,
            min_qubits=3,
            plugin_config=unitary_synthesis_plugin_config,
            target=target,
        )
    )
    unroll_3q.append(HighLevelSynthesis())
    unroll_3q.append(Unroll3qOrMore(target=target, basis_gates=basis_gates))
    return unroll_3q


def generate_embed_passmanager(coupling_map):
    """Generate a layout embedding :class:`~qiskit.transpiler.PassManager`

    This is used to generate a :class:`~qiskit.transpiler.PassManager` object
    that can be used to expand and apply an initial layout to a circuit

    Args:
        coupling_map (CouplingMap): The coupling map for the backend to embed
            the circuit to.
    Returns:
        PassManager: The embedding passmanager that assumes the layout property
            set has been set in earlier stages
    """
    return PassManager([FullAncillaAllocation(coupling_map), EnlargeWithAncilla(), ApplyLayout()])


def _trivial_not_perfect(property_set):
    # Verify that a trivial layout is perfect. If trivial_layout_score > 0
    # the layout is not perfect. The layout is unconditionally set by trivial
    # layout so we need to clear it before contuing.
    return (
        property_set["trivial_layout_score"] is not None
        and property_set["trivial_layout_score"] != 0
    )


def _apply_post_layout_condition(property_set):
    # if VF2 Post layout found a solution we need to re-apply the better
    # layout. Otherwise we can skip apply layout.
    return (
        property_set["VF2PostLayout_stop_reason"] is not None
        and property_set["VF2PostLayout_stop_reason"] is VF2PostLayoutStopReason.SOLUTION_FOUND
    )


def generate_routing_passmanager(
    routing_pass,
    target,
    coupling_map=None,
    vf2_call_limit=None,
    backend_properties=None,
    seed_transpiler=None,
    check_trivial=False,
    use_barrier_before_measurement=True,
):
    """Generate a routing :class:`~qiskit.transpiler.PassManager`

    Args:
        routing_pass (TransformationPass): The pass which will perform the
            routing
        target (Target): the :class:`~.Target` object representing the backend
        coupling_map (CouplingMap): The coupling map of the backend to route
            for
        vf2_call_limit (int): The internal call limit for the vf2 post layout
            pass. If this is ``None`` the vf2 post layout will not be run.
        backend_properties (BackendProperties): Properties of a backend to
            synthesize for (e.g. gate fidelities).
        seed_transpiler (int): Sets random seed for the stochastic parts of
            the transpiler.
        check_trivial (bool): If set to true this will condition running the
            :class:`~.VF2PostLayout` pass after routing on whether a trivial
            layout was tried and was found to not be perfect. This is only
            needed if the constructed pass manager runs :class:`~.TrivialLayout`
            as a first layout attempt and uses it if it's a perfect layout
            (as is the case with preset pass manager level 1).
        use_barrier_before_measurement (bool): If true (the default) the
            :class:`~.BarrierBeforeFinalMeasurements` transpiler pass will be run prior to the
            specified pass in the ``routing_pass`` argument.
    Returns:
        PassManager: The routing pass manager
    """

    def _run_post_layout_condition(property_set):
        # If we check trivial layout and the found trivial layout was not perfect also
        # ensure VF2 initial layout was not used before running vf2 post layout
        if not check_trivial or _trivial_not_perfect(property_set):
            vf2_stop_reason = property_set["VF2Layout_stop_reason"]
            if vf2_stop_reason is None or vf2_stop_reason != VF2LayoutStopReason.SOLUTION_FOUND:
                return True
        return False

    routing = PassManager()
    routing.append(CheckMap(coupling_map))

    def _swap_condition(property_set):
        return not property_set["is_swap_mapped"]

    if use_barrier_before_measurement:
        routing.append([BarrierBeforeFinalMeasurements(), routing_pass], condition=_swap_condition)
    else:
        routing.append([routing_pass], condition=_swap_condition)

    if (target is not None or backend_properties is not None) and vf2_call_limit is not None:
        routing.append(
            VF2PostLayout(
                target,
                coupling_map,
                backend_properties,
                seed_transpiler,
                call_limit=vf2_call_limit,
                strict_direction=False,
            ),
            condition=_run_post_layout_condition,
        )
        routing.append(ApplyLayout(), condition=_apply_post_layout_condition)

    return routing


def generate_pre_op_passmanager(target=None, coupling_map=None, remove_reset_in_zero=False):
    """Generate a pre-optimization loop :class:`~qiskit.transpiler.PassManager`

    This pass manager will check to ensure that directionality from the coupling
    map is respected

    Args:
        target (Target): the :class:`~.Target` object representing the backend
        coupling_map (CouplingMap): The coupling map to use
        remove_reset_in_zero (bool): If ``True`` include the remove reset in
            zero pass in the generated PassManager
    Returns:
        PassManager: The pass manager

    """
    pre_opt = PassManager()
    if coupling_map:
        pre_opt.append(CheckGateDirection(coupling_map, target=target))

        def _direction_condition(property_set):
            return not property_set["is_direction_mapped"]

        pre_opt.append([GateDirection(coupling_map, target=target)], condition=_direction_condition)
    if remove_reset_in_zero:
        pre_opt.append(RemoveResetInZeroState())
    return pre_opt


def generate_translation_passmanager(
    target,
    basis_gates=None,
    method="translator",
    approximation_degree=None,
    coupling_map=None,
    backend_props=None,
    unitary_synthesis_method="default",
    unitary_synthesis_plugin_config=None,
):
    """Generate a basis translation :class:`~qiskit.transpiler.PassManager`

    Args:
        target (Target): the :class:`~.Target` object representing the backend
        basis_gates (list): A list of str gate names that represent the basis
            gates on the backend target
        method (str): The basis translation method to use
        approximation_degree (float): The heuristic approximation degree to
            use. Can be between 0 and 1.
        coupling_map (CouplingMap): the coupling map of the backend
            in case synthesis is done on a physical circuit. The
            directionality of the coupling_map will be taken into
            account if pulse_optimize is True/None and natural_direction
            is True/None.
        unitary_synthesis_plugin_config (dict): The optional dictionary plugin
            configuration, this is plugin specific refer to the specified plugin's
            documenation for how to use.
        backend_props (BackendProperties): Properties of a backend to
            synthesize for (e.g. gate fidelities).
        unitary_synthesis_method (str): The unitary synthesis method to use

    Returns:
        PassManager: The basis translation pass manager

    Raises:
        TranspilerError: If the ``method`` kwarg is not a valid value
    """
    if method == "unroller":
        unroll = [Unroller(basis_gates)]
    elif method == "translator":
        unroll = [
            # Use unitary synthesis for basis aware decomposition of
            # UnitaryGates before custom unrolling
            UnitarySynthesis(
                basis_gates,
                approximation_degree=approximation_degree,
                coupling_map=coupling_map,
                backend_props=backend_props,
                plugin_config=unitary_synthesis_plugin_config,
                method=unitary_synthesis_method,
                target=target,
            ),
            HighLevelSynthesis(),
            UnrollCustomDefinitions(sel, basis_gates),
            BasisTranslator(sel, basis_gates, target),
        ]
    elif method == "synthesis":
        unroll = [
            # # Use unitary synthesis for basis aware decomposition of
            # UnitaryGates > 2q before collection
            UnitarySynthesis(
                basis_gates,
                approximation_degree=approximation_degree,
                coupling_map=coupling_map,
                backend_props=backend_props,
                plugin_config=unitary_synthesis_plugin_config,
                method=unitary_synthesis_method,
                min_qubits=3,
                target=target,
            ),
            HighLevelSynthesis(),
            Unroll3qOrMore(target=target, basis_gates=basis_gates),
            Collect2qBlocks(),
            Collect1qRuns(),
            ConsolidateBlocks(basis_gates=basis_gates, target=target),
            UnitarySynthesis(
                basis_gates=basis_gates,
                approximation_degree=approximation_degree,
                coupling_map=coupling_map,
                backend_props=backend_props,
                plugin_config=unitary_synthesis_plugin_config,
                method=unitary_synthesis_method,
                target=target,
            ),
            HighLevelSynthesis(),
        ]
    else:
        raise TranspilerError("Invalid translation method %s." % method)
    return PassManager(unroll)


def generate_scheduling(instruction_durations, scheduling_method, timing_constraints, inst_map):
    """Generate a post optimization scheduling :class:`~qiskit.transpiler.PassManager`

    Args:
        instruction_durations (dict): The dictionary of instruction durations
        scheduling_method (str): The scheduling method to use, can either be
            ``'asap'``/``'as_soon_as_possible'`` or
            ``'alap'``/``'as_late_as_possible'``
        timing_constraints (TimingConstraints): Hardware time alignment restrictions.
        inst_map (InstructionScheduleMap): Mapping object that maps gate to schedule.

    Returns:
        PassManager: The scheduling pass manager

    Raises:
        TranspilerError: If the ``scheduling_method`` kwarg is not a valid value
    """
    scheduling = PassManager()
    if inst_map and inst_map.has_custom_gate():
        scheduling.append(PulseGates(inst_map=inst_map))
    if scheduling_method:
        # Do scheduling after unit conversion.
        scheduler = {
            "alap": ALAPScheduleAnalysis,
            "as_late_as_possible": ALAPScheduleAnalysis,
            "asap": ASAPScheduleAnalysis,
            "as_soon_as_possible": ASAPScheduleAnalysis,
        }
        scheduling.append(TimeUnitConversion(instruction_durations))
        try:
            scheduling.append(scheduler[scheduling_method](instruction_durations))
        except KeyError as ex:
            raise TranspilerError("Invalid scheduling method %s." % scheduling_method) from ex
    elif instruction_durations:
        # No scheduling. But do unit conversion for delays.
        def _contains_delay(property_set):
            return property_set["contains_delay"]

        scheduling.append(ContainsInstruction("delay"))
        scheduling.append(TimeUnitConversion(instruction_durations), condition=_contains_delay)
    if (
        timing_constraints.granularity != 1
        or timing_constraints.min_length != 1
        or timing_constraints.acquire_alignment != 1
        or timing_constraints.pulse_alignment != 1
    ):
        # Run alignment analysis regardless of scheduling.

        def _require_alignment(property_set):
            return property_set["reschedule_required"]

        scheduling.append(
            InstructionDurationCheck(
                acquire_alignment=timing_constraints.acquire_alignment,
                pulse_alignment=timing_constraints.pulse_alignment,
            )
        )
        scheduling.append(
            ConstrainedReschedule(
                acquire_alignment=timing_constraints.acquire_alignment,
                pulse_alignment=timing_constraints.pulse_alignment,
            ),
            condition=_require_alignment,
        )
        scheduling.append(
            ValidatePulseGates(
                granularity=timing_constraints.granularity,
                min_length=timing_constraints.min_length,
            )
        )
    if scheduling_method:
        # Call padding pass if circuit is scheduled
        scheduling.append(PadDelay())

    return scheduling


def get_vf2_call_limit(
    optimization_level: int,
    layout_method: Optional[str] = None,
    initial_layout: Optional[Layout] = None,
) -> Optional[int]:
    """Get the vf2 call limit for vf2 based layout passes."""
    vf2_call_limit = None
    if layout_method is None and initial_layout is None:
        if optimization_level == 1:
            vf2_call_limit = int(5e4)  # Set call limit to ~100ms with retworkx 0.10.2
        elif optimization_level == 2:
            vf2_call_limit = int(5e6)  # Set call limit to ~10 sec with retworkx 0.10.2
        elif optimization_level == 3:
            vf2_call_limit = int(3e7)  # Set call limit to ~60 sec with retworkx 0.10.2
    return vf2_call_limit
