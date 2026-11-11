"""Simplified reactor model: one-group point kinetics + lumped coolant thermal model.

EDUCATIONAL ONLY. This is a toy model for a portfolio project, not a safety or design tool.
Parameter values are textbook orders of magnitude, and some are deliberately adjusted
(noted inline) so the dynamics are visible on a dashboard.

Model
-----
Point kinetics, one delayed-neutron group, with the precursor concentration normalised
so that ``c == n`` at equilibrium (this keeps both state variables near 1.0)::

    dn/dt = ((rho - beta) * n + beta * c) / Lambda
    dc/dt = lambda * (n - c)

``n`` is power as a fraction of full power. Reactivity::

    rho = rho_rods(x) - rho_rods(x_crit) + alpha_T * (T - T_ref)

The rods' integral worth follows the classic S-curve you get from a sinusoidal
differential worth: ``rho_rods(x) = -W * (x - sin(2 pi x) / (2 pi))``, x = insertion
fraction. The reactor is critical at full power with rods at ``x_crit`` and coolant at
``T_ref``.

Lumped coolant energy balance (power heats the coolant, a heat sink removes heat)::

    C_th * dT/dt = P_full * n - UA * (T - T_sink)

Integration: classical RK4 on a fixed step (1 ms by default)
-------------------------------------------------------------
The kinetics equations are stiff: the prompt eigenvalue is roughly (rho - beta) / Lambda,
about -1000 1/s right after a scram. Any explicit method has to keep |h * eigenvalue|
inside its stability region: below 2 for forward Euler, about 2.8 for RK4. At h = 1 ms
both methods are stable. RK4 is still the better choice: its error is O(h^4) rather
than O(h), so a 1 ms step tracks the prompt jump accurately, whereas Euler would need
a far smaller step for the same accuracy. Four derivative evaluations per step is cheap
for a three-variable system.

Rods move at constant speed within a substep (clamped at the target), so their position
is linear in time across it. RK4 therefore evaluates rod reactivity at the substep's start,
midpoint and end positions, the same times at which it evaluates its k1, k2/k3 and k4
stages. Holding the rods fixed over the substep would add an O(h) error during a scram.

One-group caveat: after a scram, neutron power here settles onto a period of about -14 s.
A real reactor's tail is about -80 s, because the longest-lived precursor group
(half-life about 55 s) dominates. So this model looks shut down faster than reality.

Not modelled: decay heat (about 6-7 % of full power just after shutdown, so real
*thermal* power falls much more slowly than neutron power), xenon, soluble boron,
spatial effects and multiple delayed groups.
"""

import math
from dataclasses import dataclass

PCM = 1e-5  # 1 pcm = 1e-5 delta-k/k


@dataclass(frozen=True, slots=True)
class ReactorParams:
    # --- Kinetics -------------------------------------------------------------------
    # Total delayed-neutron fraction for U-235 thermal fission (Keepin; Lamarsh &
    # Baratta, "Introduction to Nuclear Engineering", Table 7.4).
    beta: float = 0.0065
    # One-group effective precursor decay constant [1/s]. The textbook one-group value is
    # about 0.08 1/s (Lamarsh & Baratta use 0.0767).
    decay_constant: float = 0.08
    # Prompt neutron generation time [s]. LWRs are about 2e-5 s. We use 1e-4 s (the upper
    # end for thermal reactors) to make the equations less stiff. It barely changes
    # behaviour on the delayed time scale that dominates what you see.
    generation_time: float = 1e-4

    # --- Control rods ---------------------------------------------------------------
    # Total rod worth (delta-k/k): 10 000 pcm, the order of a PWR's combined control and
    # shutdown banks.
    total_rod_worth: float = 0.10
    # Insertion (%) at which the reactor is critical at full power. At power, PWR rods
    # sit near the top of the core. Soluble boron, not modelled here, holds down the
    # remaining excess reactivity.
    critical_rod_insertion_percent: float = 20.0
    # Normal drive speed (%/s). A PWR rod drive steps about 72 steps/min over a
    # 228-step stroke, i.e. full travel in about 3 min, which is about 0.5 %/s.
    rod_speed_percent_per_s: float = 0.5
    # Scram speed (%/s). Rods fall under gravity in about 2 s; technical specifications
    # typically require a rod drop time of 2.7 s or less. Modelled as a constant speed.
    scram_speed_percent_per_s: float = 50.0

    # --- Feedback -------------------------------------------------------------------
    # Lumped temperature coefficient (delta-k/k per K): -20 pcm/K, the same order as a
    # PWR's moderator coefficient plus fuel Doppler. Negative means stable.
    temperature_coefficient_per_k: float = -20 * PCM

    # --- Thermal --------------------------------------------------------------------
    # Thermal rating of a large PWR (e.g. Westinghouse 4-loop, about 3400 MWt).
    full_power_mw: float = 3000.0
    # Heat-sink temperature (deg C), roughly a PWR cold-leg temperature.
    heat_sink_temp_c: float = 290.0
    # Heat removal coefficient UA (MW/K). Chosen so full power raises the coolant 20 K
    # above the sink, giving about 310 deg C, close to a PWR's average coolant temperature.
    heat_transfer_mw_per_k: float = 150.0
    # Lumped heat capacity (MJ/K). Deliberately small: tau = C/UA = 5 s, so temperature
    # moves on a time scale you can watch. A real primary loop is far more sluggish.
    heat_capacity_mj_per_k: float = 750.0

    # --- Numerics -------------------------------------------------------------------
    max_step_s: float = 1e-3

    @property
    def full_power_temp_rise_k(self) -> float:
        return self.full_power_mw / self.heat_transfer_mw_per_k

    @property
    def reference_temp_c(self) -> float:
        """Coolant temperature at full-power equilibrium (zero feedback reactivity here)."""
        return self.heat_sink_temp_c + self.full_power_temp_rise_k

    @property
    def thermal_time_constant_s(self) -> float:
        return self.heat_capacity_mj_per_k / self.heat_transfer_mw_per_k


@dataclass(frozen=True, slots=True)
class ReactorState:
    """Read-only snapshot, suitable for serialising to the frontend."""

    time_s: float
    power_percent: float
    coolant_temp_c: float
    rod_position_percent: float  # 0 = fully withdrawn, 100 = fully inserted
    rod_target_percent: float
    # Instantaneous period n / (dn/dt) in seconds. None means effectively infinite
    # (|period| > PERIOD_INFINITE_S, i.e. steady). Negative means power is falling.
    reactor_period_s: float | None
    reactivity_pcm: float
    scrammed: bool


PERIOD_INFINITE_S = 1e4


def rod_worth_curve(insertion_fraction: float) -> float:
    """Integral rod worth as a fraction of total worth (S-curve), for x in [0, 1]."""
    x = insertion_fraction
    return x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class Reactor:
    """Fixed-step simulated reactor. Advance it with :meth:`step`."""

    def __init__(
        self, params: ReactorParams | None = None, *, initial_power_percent: float = 100.0
    ) -> None:
        self.params = params or ReactorParams()
        if initial_power_percent <= 0.0:
            raise ValueError("initial_power_percent must be positive (no neutron source)")

        p = self.params
        n0 = initial_power_percent / 100.0
        self._time = 0.0
        self._n = n0
        self._c = n0  # precursors in equilibrium with power
        self._temp = p.heat_sink_temp_c + p.full_power_temp_rise_k * n0
        self._rod = self._critical_rod_position(self._temp)
        self._rod_target = self._rod
        self._scrammed = False

    # --- Controls ---------------------------------------------------------------------

    def set_rod_target(self, insertion_percent: float) -> None:
        """Drive rods towards a target at normal speed. Ignored while scrammed."""
        if self._scrammed:
            return
        self._rod_target = _clamp(insertion_percent, 0.0, 100.0)

    def scram(self) -> None:
        """Trip the reactor: drive all rods fully in at scram speed and latch."""
        self._scrammed = True
        self._rod_target = 100.0

    def reset_scram(self) -> None:
        """Clear the scram latch. Rods stay where they are until given a new target."""
        self._scrammed = False
        self._rod_target = self._rod

    # --- Simulation -------------------------------------------------------------------

    def step(self, dt: float) -> ReactorState:
        """Advance by ``dt`` seconds in equal substeps no longer than ``max_step_s``."""
        if dt < 0.0:
            raise ValueError("dt must be non-negative")
        if dt == 0.0:
            return self.state
        substeps = math.ceil(dt / self.params.max_step_s - 1e-9)
        h = dt / substeps
        for _ in range(substeps):
            rod_start = self._rod
            self._move_rods(h)
            self._rk4(h, rod_start, self._rod)
            self._time += h
        return self.state

    @property
    def state(self) -> ReactorState:
        rho = self._reactivity(self._rod, self._temp)
        dn, _, _ = self._derivatives(self._n, self._c, self._temp, self._rod_rho(self._rod))
        return ReactorState(
            time_s=self._time,
            power_percent=self._n * 100.0,
            coolant_temp_c=self._temp,
            rod_position_percent=self._rod,
            rod_target_percent=self._rod_target,
            reactor_period_s=self._period(self._n, dn),
            reactivity_pcm=rho / PCM,
            scrammed=self._scrammed,
        )

    # --- Internals --------------------------------------------------------------------

    def _rod_rho(self, rod_percent: float) -> float:
        """Rod reactivity relative to the full-power critical position."""
        p = self.params
        x = rod_percent / 100.0
        x_crit = p.critical_rod_insertion_percent / 100.0
        return -p.total_rod_worth * (rod_worth_curve(x) - rod_worth_curve(x_crit))

    def _feedback_rho(self, temp_c: float) -> float:
        p = self.params
        return p.temperature_coefficient_per_k * (temp_c - p.reference_temp_c)

    def _reactivity(self, rod_percent: float, temp_c: float) -> float:
        return self._rod_rho(rod_percent) + self._feedback_rho(temp_c)

    def _derivatives(
        self, n: float, c: float, temp: float, rod_rho: float
    ) -> tuple[float, float, float]:
        p = self.params
        rho = rod_rho + self._feedback_rho(temp)
        dn = ((rho - p.beta) * n + p.beta * c) / p.generation_time
        dc = p.decay_constant * (n - c)
        dtemp = (
            p.full_power_mw * n - p.heat_transfer_mw_per_k * (temp - p.heat_sink_temp_c)
        ) / p.heat_capacity_mj_per_k
        return dn, dc, dtemp

    def _rk4(self, h: float, rod_start: float, rod_end: float) -> None:
        # Rod position is linear over the substep: sample its reactivity at the RK4 stage times.
        rho_start = self._rod_rho(rod_start)
        rho_mid = self._rod_rho(0.5 * (rod_start + rod_end))
        rho_end = self._rod_rho(rod_end)
        n, c, t = self._n, self._c, self._temp

        k1 = self._derivatives(n, c, t, rho_start)
        k2 = self._derivatives(
            n + 0.5 * h * k1[0], c + 0.5 * h * k1[1], t + 0.5 * h * k1[2], rho_mid
        )
        k3 = self._derivatives(
            n + 0.5 * h * k2[0], c + 0.5 * h * k2[1], t + 0.5 * h * k2[2], rho_mid
        )
        k4 = self._derivatives(n + h * k3[0], c + h * k3[1], t + h * k3[2], rho_end)

        self._n = n + h / 6.0 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        self._c = c + h / 6.0 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        self._temp = t + h / 6.0 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        self._n = max(self._n, 0.0)  # guard against round-off; physically n >= 0

    def _move_rods(self, h: float) -> None:
        p = self.params
        speed = p.scram_speed_percent_per_s if self._scrammed else p.rod_speed_percent_per_s
        delta = self._rod_target - self._rod
        max_move = speed * h
        self._rod = (
            self._rod_target
            if abs(delta) <= max_move
            else self._rod + math.copysign(max_move, delta)
        )

    def _critical_rod_position(self, temp_c: float) -> float:
        """Rod insertion (%) giving zero total reactivity at ``temp_c``, via bisection."""
        low, high = 0.0, 100.0  # reactivity decreases monotonically with insertion
        if self._reactivity(low, temp_c) < 0.0 or self._reactivity(high, temp_c) > 0.0:
            raise ValueError("No critical rod position exists for this power level")
        for _ in range(60):
            mid = 0.5 * (low + high)
            if self._reactivity(mid, temp_c) > 0.0:
                low = mid
            else:
                high = mid
        return 0.5 * (low + high)

    @staticmethod
    def _period(n: float, dn_dt: float) -> float | None:
        if n <= 0.0 or dn_dt == 0.0:
            return None
        period = n / dn_dt
        return None if abs(period) > PERIOD_INFINITE_S else period
