import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../api/types";
import { AuthContext } from "../auth/context";
import { roleAllows } from "../auth/roles";
import { alarm } from "../test/fakes";
import { AlarmBanner } from "./AlarmBanner";
import { AlarmList } from "./AlarmList";
import { Header } from "./Header";
import { RodControl } from "./RodControl";
import { ScramControl } from "./ScramControl";
import { niceTicks } from "../chartTicks";

afterEach(cleanup);

const ENVELOPE = { min_insertion_percent: 10, max_withdraw_step_percent: 5 };
const ROLES: Role[] = ["viewer", "operator", "supervisor"];

function scramProps(role: Role, overrides: Partial<Parameters<typeof ScramControl>[0]> = {}) {
  return {
    scrammed: false,
    rodPosition: 20,
    canScram: roleAllows(role, "operator"),
    canReset: roleAllows(role, "supervisor"),
    onScram: vi.fn(() => Promise.resolve()),
    onReset: vi.fn(() => Promise.resolve()),
    ...overrides,
  };
}

describe("SCRAM control", () => {
  it.each(ROLES)("%s: cover enabled only for operators and supervisors", (role) => {
    render(<ScramControl {...scramProps(role)} />);

    const cover = screen.getByRole("button", { name: "Lift cover to SCRAM" });
    expect((cover as HTMLButtonElement).disabled).toBe(role === "viewer");
  });

  it("needs two steps: lift the cover, then press SCRAM", async () => {
    const user = userEvent.setup();
    const props = scramProps("operator");
    render(<ScramControl {...props} />);

    expect(screen.queryByRole("button", { name: "SCRAM" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Lift cover to SCRAM" }));
    expect(props.onScram).not.toHaveBeenCalled(); // lifting the cover does nothing by itself

    await user.click(screen.getByRole("button", { name: "SCRAM" }));
    expect(props.onScram).toHaveBeenCalledOnce();
  });

  it("closing the cover or pressing Escape disarms without scramming", async () => {
    const user = userEvent.setup();
    const props = scramProps("operator");
    render(<ScramControl {...props} />);

    await user.click(screen.getByRole("button", { name: "Lift cover to SCRAM" }));
    await user.click(screen.getByRole("button", { name: "Close cover" }));
    expect(screen.queryByRole("button", { name: "SCRAM" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Lift cover to SCRAM" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: "SCRAM" })).toBeNull();
    expect(props.onScram).not.toHaveBeenCalled();
  });

  it("the cover closes by itself after 10 seconds", () => {
    vi.useFakeTimers();
    try {
      render(<ScramControl {...scramProps("operator")} />);
      act(() => {
        screen.getByRole("button", { name: "Lift cover to SCRAM" }).click();
      });
      expect(screen.getByRole("button", { name: "SCRAM" })).toBeTruthy();

      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(screen.queryByRole("button", { name: "SCRAM" })).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the error if the scram is refused", async () => {
    const user = userEvent.setup();
    const props = scramProps("operator", {
      onScram: vi.fn(() => Promise.reject(new Error("Reactor is already scrammed"))),
    });
    render(<ScramControl {...props} />);

    await user.click(screen.getByRole("button", { name: "Lift cover to SCRAM" }));
    await user.click(screen.getByRole("button", { name: "SCRAM" }));

    expect(screen.getByRole("alert").textContent).toBe("Reactor is already scrammed");
  });

  it.each(ROLES)("%s after a scram: only a supervisor gets the reset button", (role) => {
    render(<ScramControl {...scramProps(role, { scrammed: true, rodPosition: 100 })} />);

    const reset = screen.queryByRole("button", { name: "Reset scram" });
    expect(reset !== null).toBe(role === "supervisor");
  });

  it("reset waits until the rods are fully in", () => {
    render(<ScramControl {...scramProps("supervisor", { scrammed: true, rodPosition: 63 })} />);

    const reset = screen.getByRole<HTMLButtonElement>("button", { name: "Reset scram" });
    expect(reset.disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("inserting: 63.0 %");
  });
});

function rodProps(role: Role, overrides: Partial<Parameters<typeof RodControl>[0]> = {}) {
  return {
    position: 20,
    target: 20,
    scrammed: false,
    envelope: ENVELOPE,
    canOperate: roleAllows(role, "operator"),
    onMove: vi.fn(() => Promise.resolve()),
    ...overrides,
  };
}

describe("Rod control", () => {
  it.each(ROLES)("%s: controls enabled only for operators and supervisors", (role) => {
    render(<RodControl {...rodProps(role)} />);

    for (const name of ["Withdraw 1 %", "Insert 1 %"]) {
      expect(screen.getByRole<HTMLButtonElement>("button", { name }).disabled).toBe(role === "viewer");
    }
    expect(screen.getByLabelText<HTMLInputElement>("New target (% inserted)").disabled).toBe(
      role === "viewer",
    );
  });

  it("sends a valid target", async () => {
    const user = userEvent.setup();
    const props = rodProps("operator");
    render(<RodControl {...props} />);

    await user.type(screen.getByLabelText("New target (% inserted)"), "17.5");
    await user.click(screen.getByRole("button", { name: "Move rods" }));

    expect(props.onMove).toHaveBeenCalledWith(17.5);
    expect(screen.getByRole("status").textContent).toBe("Rods moving to 17.5 %");
  });

  it.each([
    ["14", "withdraw rods at most 5 %"],
    ["9", "can't be withdrawn above 10 % inserted"],
  ])("rejects %s before sending it", async (value, reason) => {
    const user = userEvent.setup();
    const props = rodProps("operator");
    render(<RodControl {...props} />);

    await user.type(screen.getByLabelText("New target (% inserted)"), value);
    await user.click(screen.getByRole("button", { name: "Move rods" }));

    expect(props.onMove).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain(reason);
  });

  it("is locked while scrammed", () => {
    render(<RodControl {...rodProps("supervisor", { scrammed: true })} />);

    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Insert 1 %" }).disabled).toBe(true);
  });
});

describe("Alarm list", () => {
  it.each(ROLES)("%s: acknowledge buttons only for operators and supervisors", (role) => {
    render(
      <AlarmList
        alarms={[alarm("ACTIVE_UNACKED")]}
        canAck={roleAllows(role, "operator")}
        onAck={() => Promise.resolve()}
      />,
    );

    const button = screen.queryByRole("button", { name: "Acknowledge" });
    expect(button !== null).toBe(role !== "viewer");
  });

  it("offers acknowledge only where there is something to acknowledge", () => {
    render(
      <AlarmList
        alarms={[
          alarm("ACTIVE_UNACKED", { id: "1" }),
          alarm("ACTIVE_ACKED", { id: "2", code: "HI_TEMP" }),
          alarm("CLEARED_UNACKED", { id: "3", code: "SHORT_PERIOD" }),
        ]}
        canAck
        onAck={() => Promise.resolve()}
      />,
    );

    expect(screen.getAllByRole("button", { name: "Acknowledge" })).toHaveLength(2);
  });
});

describe("Alarm banner", () => {
  it("flashes for unacknowledged, steady amber for acknowledged, calm otherwise", () => {
    const { rerender } = render(<AlarmBanner alarms={[alarm("ACTIVE_UNACKED")]} scrammed={false} />);
    expect(screen.getByTestId("alarm-banner").className).toContain("banner-unacked");

    rerender(<AlarmBanner alarms={[alarm("ACTIVE_ACKED")]} scrammed={false} />);
    expect(screen.getByTestId("alarm-banner").className).toContain("banner-acked");

    rerender(<AlarmBanner alarms={[]} scrammed={false} />);
    expect(screen.getByTestId("alarm-banner").textContent).toBe("No active alarms");
  });
});

describe("Header", () => {
  it.each(ROLES)("%s: audit log link only for supervisors", (role) => {
    render(
      <AuthContext.Provider
        value={{
          user: { id: 1, username: role, role },
          loading: false,
          expired: false,
          login: () => Promise.resolve(),
          logout: () => undefined,
          can: (required) => roleAllows(role, required),
        }}
      >
        <MemoryRouter>
          <Header status="live" />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    expect(screen.queryByRole("link", { name: "Audit log" }) !== null).toBe(role === "supervisor");
    expect(screen.getByTestId("role").textContent.toLowerCase()).toBe(role);
  });
});

describe("Connection status", () => {
  it("counts down to the next retry from the moment the connection drops", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-11-20T12:00:00Z"));
      const auth = {
        user: { id: 1, username: "v", role: "viewer" as const },
        loading: false,
        expired: false,
        login: () => Promise.resolve(),
        logout: () => undefined,
        can: () => false,
      };
      const view = (status: "live" | "reconnecting", retryAt: number | null) => (
        <AuthContext.Provider value={auth}>
          <MemoryRouter>
            <Header status={status} retryAt={retryAt} />
          </MemoryRouter>
        </AuthContext.Provider>
      );
      const { rerender } = render(view("live", null));
      act(() => {
        vi.advanceTimersByTime(60_000); // a minute of healthy connection
      });

      rerender(view("reconnecting", Date.now() + 4000));
      expect(screen.getByTestId("connection").textContent).toBe("Connection lost. Retrying in 4 s");
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.getByTestId("connection").textContent).toBe("Connection lost. Retrying in 2 s");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("niceTicks", () => {
  it.each([
    [90, 110, [90, 95, 100, 105, 110]], // steady state
    [5.8, 110, [0, 25, 50, 75, 100, 125]], // after a scram
    [306, 316, [306, 308, 310, 312, 314, 316]], // coolant, steady
    [90, 131.7, [90, 100, 110, 120, 130, 140]], // after a rod withdrawal
  ])("%s to %s -> even round steps", (low, high, expected) => {
    expect(niceTicks(low, high)).toEqual(expected);
  });
});
