from app.sim.reactor import ReactorState


def make_state(
    power: float = 100.0, temp: float = 310.0, period: float | None = None
) -> ReactorState:
    return ReactorState(
        time_s=0.0,
        power_percent=power,
        coolant_temp_c=temp,
        rod_position_percent=20.0,
        rod_target_percent=20.0,
        reactor_period_s=period,
        reactivity_pcm=0.0,
        scrammed=False,
    )


NORMAL_STATE = make_state()
HIGH_POWER_STATE = make_state(power=110.0)
