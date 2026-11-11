from dataclasses import replace

import pytest

from app.sim.reactor import PCM, Reactor, ReactorParams, rod_worth_curve


def no_feedback() -> ReactorParams:
    return replace(ReactorParams(), temperature_coefficient_per_k=0.0)


def run_until(reactor: Reactor, t_end: float) -> None:
    reactor.step(t_end - reactor.state.time_s)


# --- Steady state -------------------------------------------------------------------


def test_starts_critical_at_full_power() -> None:
    state = Reactor().state

    assert state.power_percent == pytest.approx(100.0)
    assert state.coolant_temp_c == pytest.approx(ReactorParams().reference_temp_c)
    assert state.rod_position_percent == pytest.approx(20.0)
    assert state.reactivity_pcm == pytest.approx(0.0, abs=1e-6)
    assert state.reactor_period_s is None


def test_steady_state_stays_steady() -> None:
    reactor = Reactor()

    state = reactor.step(60.0)

    assert state.power_percent == pytest.approx(100.0, abs=1e-6)
    assert state.coolant_temp_c == pytest.approx(310.0, abs=1e-6)
    assert state.rod_position_percent == pytest.approx(20.0)
    assert state.reactor_period_s is None


@pytest.mark.parametrize("power", [5.0, 50.0])
def test_part_power_equilibrium_is_steady(power: float) -> None:
    reactor = Reactor(initial_power_percent=power)
    rods_at_start = reactor.state.rod_position_percent

    state = reactor.step(30.0)

    # Lower power means cooler coolant, which adds positive reactivity, so the rods must
    # sit deeper than at full power to be critical.
    assert rods_at_start > ReactorParams().critical_rod_insertion_percent
    assert state.power_percent == pytest.approx(power, rel=1e-6)


# --- Rod motion -----------------------------------------------------------------------


def test_withdrawing_rods_raises_power() -> None:
    reactor = Reactor()

    reactor.set_rod_target(18.0)  # withdraw 2 % of stroke
    state = reactor.step(30.0)

    assert state.rod_position_percent == pytest.approx(18.0)
    assert state.power_percent > 110.0
    assert state.reactivity_pcm > 0.0
    assert state.reactor_period_s is not None
    assert state.reactor_period_s > 0.0


def test_inserting_rods_lowers_power() -> None:
    reactor = Reactor()

    reactor.set_rod_target(22.0)
    state = reactor.step(30.0)

    assert state.power_percent < 90.0
    assert state.reactor_period_s is not None
    assert state.reactor_period_s < 0.0


def test_rods_move_at_normal_drive_speed() -> None:
    reactor = Reactor()

    reactor.set_rod_target(0.0)
    state = reactor.step(2.0)

    assert state.rod_position_percent == pytest.approx(20.0 - 2.0 * 0.5)


# --- Scram ----------------------------------------------------------------------------


def test_scram_inserts_rods_fully_at_scram_speed() -> None:
    reactor = Reactor()

    reactor.scram()
    halfway = reactor.step(0.5)
    reactor.step(2.0)

    assert halfway.rod_position_percent == pytest.approx(20.0 + 0.5 * 50.0)
    assert reactor.state.rod_position_percent == pytest.approx(100.0)
    assert reactor.state.scrammed


def test_scram_brings_power_below_5_percent_within_seconds() -> None:
    reactor = Reactor()

    reactor.scram()
    after_1s = reactor.step(1.0)
    run_until(reactor, 5.0)

    # Prompt drop: most of the fall happens within about a second, then it decays on
    # the delayed-neutron time scale.
    assert after_1s.power_percent < 10.0
    assert reactor.state.power_percent < 5.0
    assert reactor.state.reactivity_pcm < -9000


def test_rod_commands_ignored_while_scrammed_until_reset() -> None:
    reactor = Reactor()
    reactor.scram()
    reactor.step(3.0)

    reactor.set_rod_target(0.0)
    reactor.step(1.0)
    assert reactor.state.rod_position_percent == pytest.approx(100.0)

    reactor.reset_scram()
    reactor.set_rod_target(90.0)
    reactor.step(1.0)
    assert not reactor.state.scrammed
    assert reactor.state.rod_position_percent == pytest.approx(99.5)


# --- Temperature feedback -------------------------------------------------------------


def test_temperature_feedback_limits_power_rise() -> None:
    with_feedback = Reactor()
    without_feedback = Reactor(no_feedback())
    for reactor in (with_feedback, without_feedback):
        reactor.set_rod_target(18.0)
        reactor.step(300.0)

    params = ReactorParams()
    inserted_rho = with_feedback.state.reactivity_pcm  # ~0 once feedback has balanced it
    rod_rho = params.total_rod_worth * (rod_worth_curve(0.20) - rod_worth_curve(0.18))
    # Equilibrium: alpha * dT == -rod_rho and dT = full-power rise * delta-n, so
    # n = 1 + rod_rho / (|alpha| * dT_full).
    expected_power = 100.0 * (
        1.0 + rod_rho / (abs(params.temperature_coefficient_per_k) * params.full_power_temp_rise_k)
    )

    assert inserted_rho == pytest.approx(0.0, abs=0.01)
    assert with_feedback.state.reactor_period_s is None  # levelled off
    assert with_feedback.state.power_percent == pytest.approx(expected_power, rel=1e-3)
    assert without_feedback.state.power_percent > 10 * with_feedback.state.power_percent


# --- Numerics & validation ------------------------------------------------------------


def test_result_is_independent_of_how_time_is_chunked() -> None:
    coarse, fine = Reactor(), Reactor()
    for reactor in (coarse, fine):
        reactor.scram()

    coarse.step(2.0)
    for _ in range(200):
        fine.step(0.01)

    assert coarse.state.time_s == pytest.approx(fine.state.time_s)
    assert coarse.state.power_percent == pytest.approx(fine.state.power_percent, rel=1e-6)


def test_rk4_converges_with_smaller_step() -> None:
    reference = Reactor(replace(ReactorParams(), max_step_s=1e-4))
    default = Reactor()
    for reactor in (reference, default):
        reactor.scram()
        reactor.step(1.0)

    assert default.state.power_percent == pytest.approx(reference.state.power_percent, rel=1e-4)


def test_rod_worth_curve_endpoints() -> None:
    assert rod_worth_curve(0.0) == pytest.approx(0.0)
    assert rod_worth_curve(0.5) == pytest.approx(0.5)
    assert rod_worth_curve(1.0) == pytest.approx(1.0)


def test_total_rod_worth_is_10000_pcm() -> None:
    assert ReactorParams().total_rod_worth / PCM == pytest.approx(10_000)


@pytest.mark.parametrize("power", [0.0, -5.0])
def test_rejects_non_positive_initial_power(power: float) -> None:
    with pytest.raises(ValueError):
        Reactor(initial_power_percent=power)


def test_rejects_negative_dt() -> None:
    with pytest.raises(ValueError):
        Reactor().step(-0.1)
